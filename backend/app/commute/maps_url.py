"""Shared Google Maps walking-directions link builder, used by both the
Commute section (national-rail only, via CRS-resolved lat/lon) and Nearest
Stations (every mode, via station_walk_distances' stored lat/lon -- issue
#76). Split out of routes/commute.py so neither caller has to duplicate the
URL format."""
from __future__ import annotations


def maps_walking_url(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> str:
    return (
        f"https://www.google.com/maps/dir/?api=1&origin={origin_lat},{origin_lon}"
        f"&destination={dest_lat},{dest_lon}&travelmode=walking"
    )
