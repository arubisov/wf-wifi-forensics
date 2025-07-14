# wf/analysis/types.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

@dataclass
class MobileTrackPoint:
    """
    Single point in a decimated mobile track.

    Parameters
    ----------
    mac : str
        MAC address of the observed device.
    ts : int
        Timestamp of the observation (seconds since epoch).
    lat : float
        Latitude in decimal degrees.
    lon : float
        Longitude in decimal degrees.
    """
    mac: str
    ts: int
    lat: float
    lon: float

@dataclass
class Obs:
    """
    Individual packet observation.

    Parameters
    ----------
    mac : str
        MAC address of the observed device.
    ts : int
        Timestamp of the observation (seconds since epoch).
    lat : float
        Latitude in decimal degrees.
    lon : float
        Longitude in decimal degrees.
    rssi : float
        Received signal strength in dBm.
    """
    mac: str
    ts: int
    lat: float
    lon: float
    rssi: float

@dataclass
class Win:
    """
    Visibility window grouping multiple observations for one MAC.

    Parameters
    ----------
    mac : str
        MAC address shared by all observations in this window.
    ts_start : int
        Timestamp of the first observation in the window.
    ts_end : int
        Timestamp of the last observation in the window.
    points : List[Obs]
        Sequence of observations within the window.
    """
    mac: str
    ts_start: int
    ts_end: int
    points: List[Obs] = field(default_factory=list)