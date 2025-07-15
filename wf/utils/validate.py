"""
Pydantic schemas to validate parser outputs.
"""

from typing import Optional
from pydantic import BaseModel


class Session(BaseModel):
    """
    Normalized record for a single session.
    """
    id: str
    mission: str
    src_file: str
    sha256: str
    start_ts: int
    end_ts: int

class Device(BaseModel):
    """
    Normalized record for a single device.
    """
    mac: str
    type: Optional[str]
    first_ts: Optional[int]
    last_ts: Optional[int]
    oui_manuf: Optional[str]
    encryption: Optional[str]
    is_randomized: bool
    ssid: Optional[str]

class Observation(BaseModel):
    """
    Normalized record for a single packet observation.
    """
    mac: Optional[str]
    session_id: Optional[str]
    ts: int
    lat: Optional[float]
    lon: Optional[float]
    rssi: Optional[int]
    channel: Optional[int]
    frequency: Optional[int]

class DrivePath(BaseModel):
    """
    Single GPS snapshot for vehicle path reconstruction.
    """
    ts: int
    lat: float
    lon: float
    
class StaticAP(BaseModel):
    """
    Normalized record for a single static access point.
    """
    mac: str
    lat_mean: float
    lon_mean: float
    loc_error_m: float
    first_seen: int
    last_seen: int
    n_obs: int
    ssid: Optional[str]
    encryption: Optional[str]
    oui_manuf: Optional[str]
    is_randomized: Optional[bool]
    type: Optional[str]

class MobileTrackPoint(BaseModel):
    """
    One decimated GPS point in a mobile track.
    """
    ts: int
    lat: float
    lon: float

class MobileTrack(BaseModel):
    """
    One moving‐device track: metadata + all points.
    """
    mac: str
    ssid: Optional[str]
    encryption: Optional[str]
    oui_manuf: Optional[str]
    is_randomized: bool
    device_type: Optional[str]
    n_obs: int
    points: list[MobileTrackPoint]
    
class UIFilter(BaseModel):
    mac: Optional[list[str]] = None
    ssid: Optional[list[str]] = None
    encryption: Optional[list[str]] = None
    oui: Optional[list[str]] = None
    randomized: Optional[bool] = None
    exclude_static: Optional[bool] = None
    exclude_mobile: Optional[bool] = None
    time_range: Optional[tuple[int, int]] = None  # UTC seconds 
    packet_count: Optional[tuple[int, int]] = None
    points_count: Optional[tuple[int, int]] = None
    area: Optional[list[tuple[float, float]]] = None  # Polygon coordinates
    # Add more as needed