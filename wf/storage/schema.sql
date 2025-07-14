PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,           -- uuid4()
    mission TEXT NOT NULL,         -- e.g. "OP_FOO"
    src_file TEXT NOT NULL,        -- original filepath
    sha256 TEXT NOT NULL,          -- hex hash of raw file
    start_ts INTEGER NOT NULL,     -- UTC seconds
    end_ts INTEGER NOT NULL        -- UTC seconds
);

CREATE TABLE IF NOT EXISTS devices (
    mac TEXT PRIMARY KEY,          -- device MAC/BSSID
    type TEXT,                     -- device_type (client/AP/bridge)
    first_ts INTEGER,              -- earliest sighting
    last_ts INTEGER,               -- latest sighting
    oui_manuf TEXT,                -- IEEE OUI lookup
    encryption TEXT,               -- e.g. “WPA2”
    is_randomized INTEGER,         -- 0/1
    ssid TEXT                      -- last seen SSID
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT NOT NULL REFERENCES devices(mac),
    session_id TEXT NOT NULL REFERENCES sessions(id),
    ts INTEGER NOT NULL,           -- UTC seconds
    lat REAL,                      -- WGS-84
    lon REAL,
    rssi INTEGER,                  -- dBm
    channel INTEGER,
    frequency INTEGER              -- in Hz
);

-- CREATE TABLE IF NOT EXISTS device_locations (
--     mac TEXT NOT NULL REFERENCES devices(mac),
--     ts INTEGER NOT NULL,
--     lat REAL,
--     lon REAL
-- );

-- -- Spatial index on observations (or device_locations) for fast bbox queries
-- CREATE VIRTUAL TABLE IF NOT EXISTS obs_rtree USING rtree(
--     id,
--     min_lat, min_lon,
--     max_lat, max_lon
-- );

-- -- Full-text lookup for manufacturer & SSID
-- CREATE VIRTUAL TABLE IF NOT EXISTS device_fts USING fts5(
--     mac,
--     manuf,
--     ssid
-- );

-- Precomputed drive-path: full vehicle GPS track for each mission
CREATE TABLE IF NOT EXISTS drive_path (
    ts      INTEGER PRIMARY KEY,
    lat     REAL    NOT NULL,
    lon     REAL    NOT NULL
);

-- Derived tables populated by `wf analyze`
CREATE TABLE IF NOT EXISTS static_ap (
    mac         TEXT    PRIMARY KEY,
    lat_mean    REAL    NOT NULL,
    lon_mean    REAL    NOT NULL,
    loc_error_m REAL    NOT NULL,
    first_seen  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL,
    n_obs       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS mobile_track (
    mac TEXT    NOT NULL,
    ts  INTEGER NOT NULL,
    lat REAL    NOT NULL,
    lon REAL    NOT NULL,
    PRIMARY KEY (mac, ts)
);