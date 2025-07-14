# wf/utils/geo.py

"""
Geospatial utility functions.
"""

import math
from typing import Tuple

def haversine(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """
    Compute the great-circle distance between two points on the Earth.

    Parameters
    ----------
    a
        (latitude, longitude) of point A, in decimal degrees.
    b
        (latitude, longitude) of point B, in decimal degrees.

    Returns
    -------
    float
        Distance between A and B in metres.
    """
    lat1, lon1 = a
    lat2, lon2 = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lam = math.radians(lon2 - lon1)
    r = 6371000.0  # Earth radius in metres
    h = math.sin(d_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(d_lam/2)**2
    return 2 * r * math.asin(math.sqrt(h))

def geometric_median(
    points: list[tuple[float,float]],
    weights: list[float],
    eps: float = 1e-6
) -> tuple[float,float]:
    """
    Compute the geometric median of a list of points (Weiszfeld's algorithm).
    """
    total_w = sum(weights)
    # start at the weighted centroid
    x_lat = sum(w * lat for (lat, _), w in zip(points, weights)) / total_w
    x_lon = sum(w * lon for (_, lon), w in zip(points, weights)) / total_w

    while True:
        num_lat = num_lon = denom = 0.0
        for (lat, lon), w in zip(points, weights):
            # distance to current estimate
            d = max(haversine((x_lat, x_lon), (lat, lon)), 1e-12)
            inv = w / d
            num_lat += inv * lat
            num_lon += inv * lon
            denom  += inv

        new_lat = num_lat / denom
        new_lon = num_lon / denom
        if haversine((x_lat, x_lon), (new_lat, new_lon)) < eps:
            return new_lat, new_lon
        x_lat, x_lon = new_lat, new_lon