"""Distance / time matrix builder (FR-003).

Two backends:

- **OSRM** public demo server (real road routing). One ``/table`` request
  returns the full N×N matrix.
- **Haversine fallback** — great-circle distance × ``DETOUR_FACTOR``
  (default 1.4) and a fixed average speed (default 25 km/h). Always
  works, no network.

Use :func:`build_matrix` to get a :class:`DistanceMatrix` with ``km[i][j]``
and ``minutes[i][j]``. Diagonal is zero.

The OSRM public demo server has no SLA — treat it as best-effort and
let the caller decide whether to retry or fall back to haversine.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Sequence

import requests

OSRM_URL = "https://router.project-osrm.org/table/v1/driving/"
DEFAULT_DETOUR_FACTOR = 1.4
DEFAULT_SPEED_KMH = 25.0
EARTH_RADIUS_KM = 6371.0

Coord = tuple[float, float]
"""``(lat, lon)`` in decimal degrees."""


@dataclass
class DistanceMatrix:
    """Row-major N×N matrices. ``km[i][j]`` = distance from i→j."""

    km: list[list[float]]
    minutes: list[list[float]]
    backend: str

    @property
    def n(self) -> int:
        return len(self.km)


def haversine_km(a: Coord, b: Coord) -> float:
    """Great-circle distance in km between two ``(lat, lon)`` points."""
    lat1, lon1 = (radians(x) for x in a)
    lat2, lon2 = (radians(x) for x in b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def _haversine_matrix(
    coords: Sequence[Coord],
    detour_factor: float = DEFAULT_DETOUR_FACTOR,
    speed_kmh: float = DEFAULT_SPEED_KMH,
) -> DistanceMatrix:
    n = len(coords)
    km = [[0.0] * n for _ in range(n)]
    minutes = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            d = haversine_km(coords[i], coords[j]) * detour_factor
            km[i][j] = d
            minutes[i][j] = d / speed_kmh * 60.0
    return DistanceMatrix(km=km, minutes=minutes, backend="haversine")


def _osrm_matrix(coords: Sequence[Coord], timeout_s: float = 30.0) -> DistanceMatrix:
    """Single OSRM ``/table`` request returning durations + distances."""
    # OSRM expects lon,lat order (not lat,lon).
    coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coords)
    url = OSRM_URL + coord_str
    r = requests.get(
        url,
        params={"annotations": "duration,distance"},
        timeout=timeout_s,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("code") != "Ok":
        raise RuntimeError(f"OSRM responded with code={body.get('code')!r}")

    distances_m = body.get("distances")
    durations_s = body.get("durations")
    if distances_m is None or durations_s is None:
        raise RuntimeError("OSRM response missing distances/durations")

    km = [[(d or 0.0) / 1000.0 for d in row] for row in distances_m]
    minutes = [[(t or 0.0) / 60.0 for t in row] for row in durations_s]
    return DistanceMatrix(km=km, minutes=minutes, backend="osrm")


def build_matrix(
    coords: Sequence[Coord],
    *,
    prefer_osrm: bool = True,
    detour_factor: float = DEFAULT_DETOUR_FACTOR,
    speed_kmh: float = DEFAULT_SPEED_KMH,
) -> DistanceMatrix:
    """Build the N×N distance + time matrix.

    Falls back to haversine if OSRM fails or ``prefer_osrm=False``.
    """
    if prefer_osrm:
        try:
            return _osrm_matrix(coords)
        except Exception as e:  # noqa: BLE001 - any failure → fallback
            print(f"  OSRM unavailable ({type(e).__name__}: {e}); using haversine")
    return _haversine_matrix(coords, detour_factor=detour_factor, speed_kmh=speed_kmh)
