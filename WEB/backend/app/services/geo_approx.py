"""Offline approximate geocoding for the directory map.

Policy (per product): use a record's real coordinates/address when available;
otherwise fall back to a *decent approximate* from its location — ZIP centroid,
then state centroid. Coordinates are never required and never gate anything; they
only place a clinician on the map.

ZIP centroids come from the bundled GeoNames US file (app/data/us_zip_centroids.json,
~41k ZIPs). No network, no rate limits.
"""
from __future__ import annotations

import json
import os

_ZIP_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "us_zip_centroids.json")
_ZIP: dict[str, list[float]] | None = None

# Coarse US state/territory centroids — last-resort approximate when no ZIP.
_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (32.8, -86.8), "AK": (64.1, -152.3), "AZ": (34.2, -111.7), "AR": (34.9, -92.4),
    "CA": (37.2, -119.4), "CO": (39.0, -105.5), "CT": (41.6, -72.7), "DE": (39.0, -75.5),
    "DC": (38.9, -77.0), "FL": (28.6, -82.4), "GA": (32.6, -83.4), "HI": (20.3, -156.4),
    "ID": (44.4, -114.6), "IL": (40.0, -89.2), "IN": (39.9, -86.3), "IA": (42.0, -93.5),
    "KS": (38.5, -98.4), "KY": (37.5, -85.3), "LA": (31.0, -92.0), "ME": (45.4, -69.2),
    "MD": (39.0, -76.8), "MA": (42.3, -71.8), "MI": (44.3, -85.4), "MN": (46.3, -94.3),
    "MS": (32.7, -89.7), "MO": (38.4, -92.5), "MT": (47.0, -109.6), "NE": (41.5, -99.8),
    "NV": (39.3, -116.6), "NH": (43.7, -71.6), "NJ": (40.1, -74.7), "NM": (34.4, -106.1),
    "NY": (42.9, -75.6), "NC": (35.6, -79.4), "ND": (47.5, -100.5), "OH": (40.3, -82.8),
    "OK": (35.6, -97.5), "OR": (43.9, -120.6), "PA": (40.9, -77.8), "RI": (41.7, -71.6),
    "SC": (33.9, -80.9), "SD": (44.4, -100.2), "TN": (35.9, -86.4), "TX": (31.5, -99.3),
    "UT": (39.3, -111.7), "VT": (44.1, -72.7), "VA": (37.5, -78.9), "WA": (47.4, -120.5),
    "WV": (38.6, -80.6), "WI": (44.6, -89.9), "WY": (43.0, -107.6), "PR": (18.2, -66.4),
}


def _zips() -> dict[str, list[float]]:
    global _ZIP
    if _ZIP is None:
        try:
            with open(_ZIP_PATH, encoding="utf-8") as fh:
                _ZIP = json.load(fh)
        except (OSError, ValueError):
            _ZIP = {}
    return _ZIP


def resolve(*, latitude=None, longitude=None, postal_code=None, state=None,
            country=None) -> tuple[float | None, float | None, str]:
    """Return (lat, lon, precision) where precision ∈ {exact, approximate, none}."""
    if latitude is not None and longitude is not None:
        return float(latitude), float(longitude), "exact"

    # ZIP centroid (US) — a decent approximate.
    if postal_code:
        z = str(postal_code).strip()[:5].zfill(5)
        hit = _zips().get(z)
        if hit:
            return hit[0], hit[1], "approximate"

    # State centroid — coarse approximate.
    if state:
        st = str(state).strip().upper()
        if st in _STATE_CENTROIDS:
            lat, lon = _STATE_CENTROIDS[st]
            return lat, lon, "approximate"

    return None, None, "none"
