"""
Kismet parser: extract drive paths, device records, and packet observations from .kismet SQLite files.
"""

import sqlite3
import json
from typing import Tuple, Optional, Iterator

from wf.utils.validate import Device, Observation, DrivePath


def frequency_to_channel(freq_hz: int) -> Optional[int]:
    """
    Convert frequency in Hz to Wi-Fi channel number.

    Parameters
    ----------
    freq_hz : int
        Frequency in Hz.

    Returns
    -------
    Optional[int]
        Wi-Fi channel number, or None if out of known bands.
    """
    # 2.4 GHz band
    if 2412000 <= freq_hz <= 2472000:
        return int((freq_hz - 2407000) / 5000)
    # 5 GHz band
    if 5005000 <= freq_hz <= 5825000:
        return int((freq_hz - 5000000) / 5000)
    return None


def is_mac_randomized(mac: str) -> bool:
    """
    Determine if a MAC is locally administered (randomized).

    Parameters
    ----------
    mac : str
        MAC address string, e.g. "AA:BB:CC:DD:EE:FF".

    Returns
    -------
    bool
        True if the locally-administered bit is set, False otherwise.
    """
    try:
        first_octet = mac.split(":")[0]
        val = int(first_octet, 16)
    except (ValueError, IndexError):
        return False
    # Locally administered bit is 0x02
    return bool(val & 0x02)


def parse_kismet(file_path: str, session_id: str) -> Tuple[Iterator[Device], Iterator[Observation], Iterator[DrivePath]]:
    """
    Read a .kismet SQLite file and return three generators:
      1) devices (Device)
      2) observations (Observation)
      3) drive_path points (DrivePath)
    """
    conn = sqlite3.connect(file_path)
    conn.row_factory = sqlite3.Row
    return _gen_devices(conn), _gen_observations(conn, session_id), _gen_drive_path(conn)

def _gen_devices(conn: sqlite3.Connection) -> Iterator[Device]:
    """
    Pull devmac, type, first_time, last_time, device JSON → Device
    """
    for row in conn.execute(
        "SELECT devmac, type, first_time, last_time, device FROM devices"
    ):
        blob = row["device"]
        data = {}
        try:
            data = json.loads(blob)
        except (ValueError, TypeError):
            pass
        yield Device(
            mac=row["devmac"],
            type=row["type"],
            first_ts=row["first_time"],
            last_ts=row["last_time"],
            oui_manuf=data.get("kismet.device.base.manuf"),
            encryption=data.get("kismet.device.base.crypt"),
            is_randomized=is_mac_randomized(row["devmac"]),
            ssid=data.get("kismet.device.base.name"),
        )

def _gen_observations(conn: sqlite3.Connection, session_id: str) -> Iterator[Observation]:
    """
    Pull ts_sec, sourcemac, frequency, lat, lon, signal → Observation
    """
    for row in conn.execute(
        """
        SELECT ts_sec, sourcemac, frequency, lat, lon, alt, speed, heading, signal, tags
          FROM packets
        """
    ):
        freq = row["frequency"]
        yield Observation(
            mac=row["sourcemac"],
            session_id=session_id,
            ts=row["ts_sec"],
            lat=row["lat"],
            lon=row["lon"],
            rssi=row["signal"],
            channel=frequency_to_channel(freq),
            frequency=freq,
        )

def _gen_drive_path(conn: sqlite3.Connection) -> Iterator[DrivePath]:
    """
    Pull GPS snapshots (snaptype == 'GPS') → DrivePath
    """
    for row in conn.execute(
        """
        SELECT ts_sec, lat, lon
          FROM snapshots
         WHERE snaptype = 'GPS'
        """
    ):
        yield DrivePath(ts=row["ts_sec"], lat=row["lat"], lon=row["lon"])