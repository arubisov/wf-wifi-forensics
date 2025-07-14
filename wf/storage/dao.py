from sqlite3 import Connection
from typing import Iterable
from wf.utils.validate import Device, Observation, DrivePath, StaticAP, MobileTrack
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
                (device.mac,
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
            (obs.mac,
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

    def add_device_location(
        self, mac: str, ts: int, lat: float, lon: float
    ) -> None:
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
        
    def get_drive_path(self) -> list[DrivePath]:
        """
        Return list of DrivePath points sorted by timestamp.
        """
        cursor = self.conn.execute(
            "SELECT ts, lat, lon FROM drive_path ORDER BY ts"
        )
        rows = cursor.fetchall()
        return [
            DrivePath(ts=row["ts"], lat=row["lat"], lon=row["lon"])
            for row in rows
        ]
        
    def get_static_ap(self) -> list[StaticAP]:
        """
        Return list of static APs.
        """
        cursor = self.conn.execute(
            """
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
        )
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

    def get_mobile_tracks(self) -> list[MobileTrack]:
        """
        Return one Track per MAC, with metadata (ssid, etc), total packet count,
        and a list of all decimated points.
        """
        cursor = self.conn.execute(
            """
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
            ORDER BY mt.mac, mt.ts
            """
        )
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
            tracks[m]["points"].append({
                "ts": row["ts"],
                "lat": row["lat"],
                "lon": row["lon"],
            })
        return [ MobileTrack(**t) for t in tracks.values() ]
        
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

    def add_static_ap_bulk(self, rows: list[tuple[str, float, float, float, int, int, int]]) -> None:
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