from sqlite3 import Connection
from typing import Iterable
from wf.utils.validate import Device, Observation, DrivePath, StaticAP, MobileTrack, UIFilter
from wf.storage.db import init_db
from wf.utils.log import get_logger
from wf.analysis.types import MobileTrackPoint

logger = get_logger(__name__)


class DAO:
    """
    Encapsulates all inserts/queries against our Wi-Fi forensics DB.
    """

    def __init__(self, db_path: str):
        """
        Create/connect and apply schema if needed.
        """
        self.conn: Connection = init_db(db_path)

    def add_session(
        self,
        session_id: str,
        mission: str,
        src_file: str,
        sha256: str,
        start_ts: int,
        end_ts: int,
    ) -> None:
        """
        Insert a new raw-file session.
        """
        self.conn.execute(
            """
            INSERT INTO sessions
              (id, mission, src_file, sha256, start_ts, end_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, mission, src_file, sha256, start_ts, end_ts),
        )
        self.conn.commit()

    def session_exists(self, sha256: str) -> bool:
        """
        Check if a session with the given SHA256 exists.
        """
        cursor = self.conn.execute(
            "SELECT 1 FROM sessions WHERE sha256 = ? LIMIT 1",
            (sha256,),
        )
        return cursor.fetchone() is not None

    def upsert_device(
        self,
        device: Device,
    ) -> None:
        """
        Insert a new device or update first_ts/last_ts and other fields.
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO devices
                  (mac, type, first_ts, last_ts, oui_manuf, encryption, is_randomized, ssid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mac) DO UPDATE SET
                  first_ts = MIN(first_ts, excluded.first_ts),
                  last_ts  = MAX(last_ts,  excluded.last_ts),
                  oui_manuf    = excluded.oui_manuf,
                  encryption   = excluded.encryption,
                  is_randomized= excluded.is_randomized,
                  ssid         = excluded.ssid
                """,
                (
                    device.mac,
                    device.type,
                    device.first_ts,
                    device.last_ts,
                    device.oui_manuf,
                    device.encryption,
                    int(device.is_randomized),
                    device.ssid,
                ),
            )

    def add_observation(
        self,
        obs: Observation,
    ) -> None:
        """
        Record a single probe/AP sighting.
        """
        self.conn.execute(
            """
            INSERT INTO observations
              (mac, session_id, ts, lat, lon, rssi, channel)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obs.mac,
                obs.session_id,
                obs.ts,
                obs.lat,
                obs.lon,
                obs.rssi,
                obs.channel,
            ),
        )
        self.conn.commit()
        # if obs.lat is not None and obs.lon is not None:
        #     # maintain spatial index
        #     rowid = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        #     self.conn.execute(
        #         "INSERT INTO obs_rtree (id, min_lat, min_lon, max_lat, max_lon) VALUES (?, ?, ?, ?, ?)",
        #         (rowid, obs.lat, obs.lon, obs.lat, obs.lon),
        #     )
        #     self.conn.commit()

    def add_devices_bulk(self, devices: Iterable[Device]) -> None:
        """
        Bulk upsert devices in a single transaction.
        """
        stmt = """
        INSERT INTO devices
          (mac, type, first_ts, last_ts, oui_manuf, encryption, is_randomized, ssid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mac) DO UPDATE SET
          first_ts      = MIN(first_ts, excluded.first_ts),
          last_ts       = MAX(last_ts,  excluded.last_ts),
          oui_manuf     = excluded.oui_manuf,
          encryption    = excluded.encryption,
          is_randomized = excluded.is_randomized,
          ssid          = excluded.ssid
        """
        params = (
            (
                d.mac,
                d.type,
                d.first_ts,
                d.last_ts,
                d.oui_manuf,
                d.encryption,
                int(d.is_randomized),
                d.ssid,
            )
            for d in devices
        )
        with self.conn:
            self.conn.executemany(stmt, params)

    def add_observations_bulk(self, observations: Iterable[Observation]) -> None:
        """
        Bulk insert observations and their spatial‐index entries
        in a single transaction.
        """
        sql_obs = """
        INSERT INTO observations
          (mac, session_id, ts, lat, lon, rssi, channel, frequency)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        sql_rtree = """
        INSERT INTO obs_rtree
          (id, min_lat, min_lon, max_lat, max_lon)
        VALUES (?, ?, ?, ?, ?)
        """
        with self.conn:
            for obs in observations:
                cur = self.conn.execute(
                    sql_obs,
                    (
                        obs.mac,
                        obs.session_id,
                        obs.ts,
                        obs.lat,
                        obs.lon,
                        obs.rssi,
                        obs.channel,
                        obs.frequency,
                    ),
                )
                # if obs.lat is not None and obs.lon is not None:
                #     self.conn.execute(
                #         sql_rtree,
                #         (cur.lastrowid, obs.lat, obs.lon, obs.lat, obs.lon),
                #     )

    def add_paths_bulk(self, paths: Iterable[DrivePath]) -> None:
        """
        Bulk insert drive_path points in a single transaction.
        """
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO drive_path (ts, lat, lon) VALUES (?, ?, ?)",
                ((p.ts, p.lat, p.lon) for p in paths),
            )

    def add_device_location(self, mac: str, ts: int, lat: float, lon: float) -> None:
        """
        Store a raw GPS fix for a device.
        """
        self.conn.execute(
            """
            INSERT INTO device_locations (mac, ts, lat, lon)
            VALUES (?, ?, ?, ?)
            """,
            (mac, ts, lat, lon),
        )
        self.conn.commit()

    def recreate_drive_path_table(self) -> None:
        """
        Drop and re-create the drive_path table.
        """
        self.conn.execute("DROP TABLE IF EXISTS drive_path")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drive_path (
                ts      INTEGER PRIMARY KEY,
                lat     REAL    NOT NULL,
                lon     REAL    NOT NULL
            )
            """
        )
        self.conn.commit()

    def recreate_classification_tables(self) -> None:
        """
        Drop & re-create the static_ap and mobile_track tables.
        """
        with self.conn:
            self.conn.execute("DROP TABLE IF EXISTS static_ap")
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS static_ap (
                    mac         TEXT    PRIMARY KEY,
                    lat_mean    REAL    NOT NULL,
                    lon_mean    REAL    NOT NULL,
                    loc_error_m REAL    NOT NULL,
                    first_seen  INTEGER NOT NULL,
                    last_seen   INTEGER NOT NULL,
                    n_obs       INTEGER NOT NULL
                )
                """
            )
            self.conn.execute("DROP TABLE IF EXISTS mobile_track")
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mobile_track (
                    mac TEXT    NOT NULL,
                    ts  INTEGER NOT NULL,
                    lat REAL    NOT NULL,
                    lon REAL    NOT NULL,
                    PRIMARY KEY (mac, ts)
                )
                """
            )

    def add_static_ap_bulk(
        self, rows: list[tuple[str, float, float, float, int, int, int]]
    ) -> None:
        """
        Bulk insert into static_ap.
        rows: (mac, lat_mean, lon_mean, loc_error_m, first_seen, last_seen, n_obs)
        """
        sql = """
        INSERT INTO static_ap
          (mac, lat_mean, lon_mean, loc_error_m, first_seen, last_seen, n_obs)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mac) DO UPDATE SET
          lat_mean    = excluded.lat_mean,
          lon_mean    = excluded.lon_mean,
          loc_error_m = excluded.loc_error_m,
          first_seen  = excluded.first_seen,
          last_seen   = excluded.last_seen,
          n_obs       = excluded.n_obs
        """
        with self.conn:
            self.conn.executemany(sql, rows)

    def add_mobile_track_bulk(self, rows: list[MobileTrackPoint]) -> None:
        """
        Bulk insert into mobile_track.
        rows: (mac, ts, lat, lon)
        """
        sql = "INSERT OR REPLACE INTO mobile_track (mac, ts, lat, lon) VALUES (?, ?, ?, ?)"
        with self.conn:
            self.conn.executemany(sql, ((row.mac, row.ts, row.lat, row.lon) for row in rows))

    def add_path(self, path: DrivePath) -> None:
        """
        Store a single GPS snapshot.
        """
        self.conn.execute(
            "INSERT INTO drive_path (ts, lat, lon) VALUES (?, ?, ?)",
            (path.ts, path.lat, path.lon),
        )
        self.conn.commit()

    def get_session_time_bounds(self, session_id: str) -> tuple[int, int]:
        """
        Return (min_ts, max_ts) for all observations in this session.
        """
        cur = self.conn.execute(
            "SELECT MIN(ts), MAX(ts) FROM observations WHERE session_id = ?",
            (session_id,),
        )
        min_ts, max_ts = cur.fetchone()
        return min_ts or 0, max_ts or 0

    def update_session_times(self, session_id: str, start_ts: int, end_ts: int) -> None:
        """
        Patch the session row with computed start/end.
        """
        self.conn.execute(
            "UPDATE sessions SET start_ts = ?, end_ts = ? WHERE id = ?",
            (start_ts, end_ts, session_id),
        )
        self.conn.commit()

    def get_max_packets(self) -> int:
        """
        return min and max packet counts across static aps and mobile tracks.
        """
        cursor = self.conn.execute(
            """
            WITH packet_counts AS (
                SELECT mac, count(1) AS count 
                FROM observations 
                GROUP BY mac    
            )
            SELECT 
                coalesce(max(count), 0) AS max_cnt
            FROM packet_counts
            """
        )
        row = cursor.fetchone()
        return row["max_cnt"]

    def get_max_mobile_points(self) -> int:
        """
        return min and max number of points per mobile track.
        """
        cursor = self.conn.execute(
            """
            WITH pt_counts AS (
              SELECT mac, COUNT(*) AS n_pts
              FROM mobile_track
              GROUP BY mac
            )
            SELECT
              COALESCE(MAX(n_pts), 0) AS max_pts
            FROM pt_counts
            """
        )
        row = cursor.fetchone()
        return row["max_pts"]

    def get_time_range(self) -> tuple[int, int]:
        """
        return min start_ts and max end_ts across all sessions.
        """
        cursor = self.conn.execute(
            "SELECT COALESCE(MIN(start_ts), 0) AS min_ts, COALESCE(MAX(end_ts), 0) AS max_ts FROM sessions"
        )
        row = cursor.fetchone()
        return row["min_ts"], row["max_ts"]

    def get_drive_path(self, filter: UIFilter) -> list[DrivePath]:
        """
        Return list of DrivePath points sorted by timestamp.
        """
        sql = "SELECT ts, lat, lon FROM drive_path"
        params: list[int] = []
        if filter.time_range:
            sql += " WHERE ts BETWEEN ? AND ?"
            params.extend(filter.time_range)
        sql += " ORDER BY ts"
        cursor = self.conn.execute(sql, tuple(params))
        rows = cursor.fetchall()
        return [DrivePath(ts=row["ts"], lat=row["lat"], lon=row["lon"]) for row in rows]

    def get_static_ap(self, filter: UIFilter) -> list[StaticAP]:
        """
        Return list of static APs.
        """
        sql = """
            SELECT 
                static_ap.mac, 
                lat_mean,
                lon_mean,
                loc_error_m,
                first_seen,
                last_seen,
                n_obs,
                ssid,
                encryption,
                oui_manuf,
                is_randomized,
                type
            FROM static_ap
            LEFT JOIN devices ON static_ap.mac = devices.mac
            """
        params: list[int] = []
        if filter.time_range:
            sql += " WHERE first_seen >= ? AND last_seen <= ?"
            params.extend(filter.time_range)
        if filter.packet_count:
            sql += " AND n_obs BETWEEN ? AND ?"
            params.extend(filter.packet_count)
        # TODO: add mac/ssid/encryption/area filters here
        cursor = self.conn.execute(sql, tuple(params))
        rows = cursor.fetchall()
        return [
            StaticAP(
                mac=row["mac"],
                lat_mean=row["lat_mean"],
                lon_mean=row["lon_mean"],
                loc_error_m=row["loc_error_m"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                n_obs=row["n_obs"],
                ssid=row["ssid"],
                encryption=row["encryption"],
                oui_manuf=row["oui_manuf"],
                is_randomized=row["is_randomized"],
                type=row["type"],
            )
            for row in rows
        ]

    def get_mobile_tracks(self, filter: UIFilter) -> list[MobileTrack]:
        """
        Return one Track per MAC, with metadata (ssid, etc), total packet count,
        and a list of all decimated points.
        """
        sql = """
            WITH obs_counts AS (
              SELECT mac, COUNT(*) AS n_obs
              FROM observations
              GROUP BY mac
            )
            SELECT
              mt.mac,
              mt.ts,
              mt.lat,
              mt.lon,
              d.ssid,
              d.encryption,
              d.oui_manuf,
              d.is_randomized,
              d.type        AS device_type,
              oc.n_obs
            FROM mobile_track mt
            LEFT JOIN devices d  ON mt.mac = d.mac
            LEFT JOIN obs_counts oc ON mt.mac = oc.mac
            """
        params: list[int] = []
        clauses: list[str] = []
        if filter.time_range:
            clauses.append("mt.ts BETWEEN ? AND ?")
            params.extend(filter.time_range)
        if filter.packet_count:
            clauses.append("oc.n_obs BETWEEN ? AND ?")
            params.extend(filter.packet_count)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY mt.mac, mt.ts"
        cursor = self.conn.execute(sql, tuple(params))
        rows = cursor.fetchall()
        tracks: dict[str, dict] = {}
        for row in rows:
            m = row["mac"]
            if m not in tracks:
                tracks[m] = {
                    "mac": m,
                    "ssid": row["ssid"],
                    "encryption": row["encryption"],
                    "oui_manuf": row["oui_manuf"],
                    "is_randomized": bool(row["is_randomized"]),
                    "device_type": row["device_type"],
                    "n_obs": row["n_obs"],
                    "points": [],
                }
            tracks[m]["points"].append(
                {
                    "ts": row["ts"],
                    "lat": row["lat"],
                    "lon": row["lon"],
                }
            )
            
        # TODO: if filter.points_count, apply post filter to remove from tracks if num points not in range of points_count
        return [MobileTrack(**t) for t in tracks.values()]

    def get_encryption_counts(self, filter: UIFilter) -> list[tuple[str, int]]:
        """
        Return counts of observations grouped by encryption type,
        filtered by time and static/mobile flags.
        """
        sql = """
        SELECT d.encryption AS encryption, COUNT(*) AS cnt
        FROM observations o
        JOIN devices d ON o.mac = d.mac
        """
        params: list[int] = []
        clauses: list[str] = []
        if filter.time_range:
            clauses.append("o.ts BETWEEN ? AND ?")
            params.extend(filter.time_range)
        if filter.exclude_static:
            clauses.append("o.mac NOT IN (SELECT mac FROM static_ap)")
        if filter.exclude_mobile:
            clauses.append("o.mac NOT IN (SELECT mac FROM mobile_track)")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " GROUP BY d.encryption"
        cursor = self.conn.execute(sql, tuple(params))

        # normalize to protocol only and re‐aggregate
        raw_counts = [(row["encryption"], row["cnt"]) for row in cursor.fetchall()]
        protocol_counts: dict[str, int] = {}
        for enc, cnt in raw_counts:
            proto = enc.split(" ")[0]
            if proto == "WPA1":
                proto = "WPA"
            # only keep our five protocols plus empty string
            if proto not in ["", "Open", "WEP", "WPA", "WPA2", "WPA3"]:
                continue
            protocol_counts[proto] = protocol_counts.get(proto, 0) + cnt
        # return protocols sorted by count in descending order
        return sorted(
            protocol_counts.items(),
            key=lambda pair: pair[1],
            reverse=True,
        )

    def get_mac_counts(self, filter: UIFilter) -> list[tuple[str, str, int]]:
        """
        Return counts of observations per MAC, filtered by time and static/mobile flags,
        ordered by descending count, limited to `limit`.
        Also returns the SSID associated with each MAC, if it exists.
        """
        sql = """
        SELECT o.mac AS mac, 
          d.ssid AS ssid,
          COUNT(*) AS cnt
        FROM observations o
        LEFT JOIN devices d ON o.mac = d.mac
        """
        params: list[int] = []
        clauses: list[str] = []
        if filter.time_range:
            clauses.append("o.ts BETWEEN ? AND ?")
            params.extend(filter.time_range)
        if filter.exclude_static:
            clauses.append("o.mac NOT IN (SELECT mac FROM static_ap)")
        if filter.exclude_mobile:
            clauses.append("o.mac NOT IN (SELECT mac FROM mobile_track)")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " GROUP BY o.mac ORDER BY cnt DESC"
        cursor = self.conn.execute(sql, tuple(params))
        return [(row["mac"], row["ssid"], row["cnt"]) for row in cursor.fetchall()]

    def get_unique_mac_count(self, filter: UIFilter) -> int:
        """
        Return count of distinct MACs in observations,
        filtered by time and static/mobile flags.
        """
        sql = "SELECT COUNT(DISTINCT o.mac) FROM observations o"
        params: list[int] = []
        clauses: list[str] = []
        if filter.time_range:
            clauses.append("o.ts BETWEEN ? AND ?")
            params.extend(filter.time_range)
        if filter.exclude_static:
            clauses.append("o.mac NOT IN (SELECT mac FROM static_ap)")
        if filter.exclude_mobile:
            clauses.append("o.mac NOT IN (SELECT mac FROM mobile_track)")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        cursor = self.conn.execute(sql, tuple(params))
        return cursor.fetchone()[0]

    def get_unique_ssid_count(self, filter: UIFilter) -> int:
        """
        Return count of distinct SSIDs in observations,
        filtered by time and static/mobile flags.
        """
        sql = """
        SELECT COUNT(DISTINCT d.ssid)
        FROM observations o
        JOIN devices d ON o.mac = d.mac
        """
        params: list[int] = []
        clauses: list[str] = []
        if filter.time_range:
            clauses.append("o.ts BETWEEN ? AND ?")
            params.extend(filter.time_range)
        if filter.exclude_static:
            clauses.append("o.mac NOT IN (SELECT mac FROM static_ap)")
        if filter.exclude_mobile:
            clauses.append("o.mac NOT IN (SELECT mac FROM mobile_track)")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        cursor = self.conn.execute(sql, tuple(params))
        return cursor.fetchone()[0]

    def get_oui_counts(self, filter: UIFilter) -> list[tuple[str, int]]:
        """
        Return counts of observations grouped by OUI manufacturer,
        filtered by time and static/mobile flags, ordered descending.
        """
        sql = """
        SELECT d.oui_manuf AS oui, COUNT(*) AS cnt
        FROM observations o
        JOIN devices d ON o.mac = d.mac
        """
        params: list[int] = []
        clauses: list[str] = []
        if filter.time_range:
            clauses.append("o.ts BETWEEN ? AND ?")
            params.extend(filter.time_range)
        if filter.exclude_static:
            clauses.append("o.mac NOT IN (SELECT mac FROM static_ap)")
        if filter.exclude_mobile:
            clauses.append("o.mac NOT IN (SELECT mac FROM mobile_track)")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " GROUP BY d.oui_manuf ORDER BY cnt DESC LIMIT 5"
        cursor = self.conn.execute(sql, tuple(params))
        return [(row["oui"], row["cnt"]) for row in cursor.fetchall()]
