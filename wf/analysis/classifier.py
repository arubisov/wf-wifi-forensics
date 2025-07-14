"""
Classify individual packet observations as co-travellers vs. static APs.

Refering to spec.md, this implements:
- Pass 0: normalization + deduplication
- Pass 1: visibility windowing
- Pass 2: stationary vs. mobile split
- Pass 3A: static AP aggregation
- Pass 3B+4: mobile track decimation
- Pass 5: QA filters
"""

from __future__ import annotations
import math
from collections import defaultdict, deque
from typing import Any, NamedTuple, List, Tuple
from wf.storage.dao import DAO
from wf.analysis.types import Obs, Win, MobileTrackPoint
from wf.analysis.config import ClassifierConfig
from wf.utils.log import get_logger
from wf.utils.geo import haversine, geometric_median

logger = get_logger(__name__)

# -----------------------------------------------------------------------------
# Configurable constants (seconds, metres)
T_MAX_GAP      = 120    # end visibility window if silent ≥ this gap
MIN_WINDOW_LEN = 1      # ignore ultra-short windows (packets)
R_STATIONARY   = 350.0  # max diameter to qualify as “stationary”
MOBILE_DECIM_D = 100.0  # metres threshold for decimation
MOBILE_DECIM_T = 30     # seconds threshold for decimation
MAX_SPEED_MS   = 200e3 / 3600  # 200 km/h in m/s
# -----------------------------------------------------------------------------

class ClassifierPipeline:
    """
    Stateful pipeline for classifying observations into static APs & mobile tracks.
    """
    def __init__(self, dao: DAO, cfg: ClassifierConfig) -> None:
        self.dao = dao
        self.cfg = cfg
        
    def run(self) -> None:
        logger.info("Starting classification")
        obs = self._load_and_normalize()
        logger.info(f"Loaded {len(obs)} observations")
        wins = self._windowize(obs)
        logger.info(f"Windowized {len(wins)} windows")
        stat_wins, mob_wins = self._split_stationary(wins)
        logger.info(f"Split {len(stat_wins)} stationary and {len(mob_wins)} mobile windows")
        static_rows = self._aggregate_static(stat_wins)
        logger.info(f"Aggregated {len(static_rows)} static APs")
        mobile_rows = self._decimate_mobile(mob_wins)
        logger.info(f"Decimated {len(mobile_rows)} mobile tracks")
        self._write_results(static_rows, mobile_rows)
        logger.info("Classification complete")

    def _load_and_normalize(self) -> list[Obs]:
        """
        Load deduped observations from database and normalize them.
        """
        raw = self.dao.conn.execute(
            "SELECT DISTINCT mac, ts, lat, lon, rssi FROM observations "
            "WHERE lat IS NOT NULL AND lon IS NOT NULL"
        ).fetchall()

        return [Obs(row["mac"], row["ts"], row["lat"], row["lon"], row["rssi"]) for row in raw]
    
    def _windowize(self, obs: list[Obs]) -> list[Win]:
        """
        Create visibility windows from observations.
        """
        wins: list[Win] = []
        
        # group by mac
        obs_by_mac: dict[str, list[Obs]] = defaultdict(list)
        for o in obs:
            obs_by_mac[o.mac].append(o)
        
        # windowize
        for mac, points in obs_by_mac.items():
            pts = sorted(points, key=lambda o: o.ts)
            cur_pts = [pts[0]]
            for prev, curr in zip(pts, pts[1:]):
                if curr.ts - prev.ts >= self.cfg.t_max_gap:
                    if len(cur_pts) >= self.cfg.min_window_len:
                        wins.append(Win(mac, cur_pts[0].ts, cur_pts[-1].ts, list(cur_pts)))
                    cur_pts = []
                cur_pts.append(curr)
            if len(cur_pts) >= self.cfg.min_window_len:
                wins.append(Win(mac, cur_pts[0].ts, cur_pts[-1].ts, list(cur_pts)))
        return wins
    
    def _split_stationary(self, wins: list[Win]) -> tuple[list[Win], list[Win]]:
        """
        Split windows into stationary & mobile.
        """
        stat_wins: list[Win] = []
        mob_wins: list[Win] = []
        for w in wins:
            # compute d_max
            maxd = 0.0
            pts = w.points
            for i in range(len(pts)):
                for j in range(i+1, len(pts)):
                    d = haversine((pts[i].lat, pts[i].lon), (pts[j].lat, pts[j].lon))
                    if d > maxd:
                        maxd = d
            if maxd <= self.cfg.r_stationary:
                stat_wins.append(w)
            else:
                mob_wins.append(w)
        return stat_wins, mob_wins

    
    def _aggregate_static(self, stat_wins: list[Win]) -> list[tuple]:
        """
        Aggregate static APs via RSSI-weighted geometric median.
        
        Before we were running Weiszfeld’s algorithm (and a full‐blast haversine loop) over every 
        raw Obs for each MAC. You can get a ~100× speed‐up by first collapsing each window into a
        single weighted centroid (and total‐weight + counts) and then running your geometric‐median
        & error loops over those window‐summaries instead of all of the raw Obs.
        """
        # 1) collapse each window to one centroid + total weight + time span + obs count
        win_centers_by_mac: dict[str, list[tuple[float, float]]] = defaultdict(list)
        win_weights_by_mac: dict[str, list[float]]           = defaultdict(list)
        ts0_by_mac:         dict[str, list[int]]             = defaultdict(list)
        ts1_by_mac:         dict[str, list[int]]             = defaultdict(list)
        n_obs_by_mac:       dict[str, int]                   = defaultdict(int)

        for w in stat_wins:
            # per-window weights & weighted centroid
            wts = [10 ** (p.rssi / 10) for p in w.points]
            tot_w = sum(wts)
            lat_c = sum(w * p.lat for w, p in zip(wts, w.points)) / tot_w
            lon_c = sum(w * p.lon for w, p in zip(wts, w.points)) / tot_w

            win_centers_by_mac[w.mac].append((lat_c, lon_c))
            win_weights_by_mac[w.mac].append(tot_w)
            ts0_by_mac[w.mac].append(w.ts_start)
            ts1_by_mac[w.mac].append(w.ts_end)
            n_obs_by_mac[w.mac] += len(w.points)

        # 2) for each MAC, run geometric median only on window-centroids
        static_rows: list[tuple] = []
        for mac, centers in win_centers_by_mac.items():
            wts      = win_weights_by_mac[mac]
            lat_med, lon_med = geometric_median(centers, wts)

            total_w = sum(wts)
            errs    = [haversine((lat_med,lon_med), c) for c in centers]
            loc_err = sum(w * e for w, e in zip(wts, errs)) / total_w

            static_rows.append((
                mac,
                lat_med,
                lon_med,
                loc_err,
                min(ts0_by_mac[mac]),
                max(ts1_by_mac[mac]),
                n_obs_by_mac[mac],
            ))
        return static_rows
    
    def _decimate_mobile(self, mob_wins: list[Win]) -> list[MobileTrackPoint]:
        """
        Decimate mobile tracks from visibility windows.

        Returns
        -------
        List of (mac, timestamp, lat, lon) for each point in
        qualifying mobile tracks (≥2 points after decimation).
        """
        
        def _decimate_track(points: list[Obs]) -> list[MobileTrackPoint]:
            """
            Apply spatial and temporal decimation to a sorted Obs list.

            Parameters
            ----------
            points
                Observations sorted by timestamp.

            Returns
            -------
            Decimated list of observations.
            """
            if not points:
                return []

            decimated: list[MobileTrackPoint] = [MobileTrackPoint(points[0].mac, points[0].ts, points[0].lat, points[0].lon)]
            last = points[0]
            for curr in points[1:]:
                dt = curr.ts - last.ts
                d = haversine((last.lat, last.lon), (curr.lat, curr.lon))
                # only keep if far enough or long enough since last
                if d >= self.cfg.mobile_decim_d or dt >= self.cfg.mobile_decim_t:
                    speed = d / max(dt, 1)
                    if speed <= self.cfg.max_speed_ms:
                        decimated.append(MobileTrackPoint(curr.mac, curr.ts, curr.lat, curr.lon))
                        last = curr
            return decimated
        
        # group by MAC
        pts_by_mac: dict[str, list[Obs]] = defaultdict(list)
        for window in mob_wins:
            pts_by_mac[window.mac].extend(window.points)
        
        # decimate each track
        mobile_rows: list[MobileTrackPoint] = []
        for mac, pts in pts_by_mac.items():
            pts = sorted(pts, key=lambda o: o.ts)
            decimated = _decimate_track(pts)
            if len(decimated) >= 2:
                mobile_rows.extend(decimated)
        return mobile_rows
    
    def _write_results(
        self,
        static: list[tuple],
        mobile: list[MobileTrackPoint]
    ) -> None:   
        """
        Write results to database.
        """
        logger.info("Recreating classification tables")
        self.dao.recreate_classification_tables()
        self.dao.add_static_ap_bulk(static)
        self.dao.add_mobile_track_bulk(mobile)