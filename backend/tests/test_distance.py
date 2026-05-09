"""Unit tests for the distance matrix (FR-003)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from smart_truck.data import distance as D


def test_haversine_known_distance() -> None:
    # 0,0 to 0,1 along the equator → about 111 km.
    d = D.haversine_km((0.0, 0.0), (0.0, 1.0))
    assert d == pytest.approx(111.19, rel=0.01)


def test_haversine_zero_for_same_point() -> None:
    p = (41.5444, 2.2143)
    assert D.haversine_km(p, p) == pytest.approx(0.0, abs=1e-9)


def test_haversine_matrix_shape_and_diagonal() -> None:
    coords = [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0)]
    m = D._haversine_matrix(coords)
    assert m.n == 3
    assert all(m.km[i][i] == 0.0 for i in range(3))
    assert all(m.minutes[i][i] == 0.0 for i in range(3))
    assert m.backend == "haversine"


def test_haversine_matrix_symmetric() -> None:
    coords = [(41.5, 2.2), (41.7, 2.4), (41.6, 2.1)]
    m = D._haversine_matrix(coords)
    for i in range(m.n):
        for j in range(m.n):
            assert m.km[i][j] == pytest.approx(m.km[j][i])


def test_build_matrix_falls_back_when_osrm_fails() -> None:
    coords = [(41.5, 2.2), (41.7, 2.4)]
    with patch.object(D, "_osrm_matrix", side_effect=RuntimeError("nope")):
        m = D.build_matrix(coords, prefer_osrm=True)
    assert m.backend == "haversine"
    assert m.n == 2


def test_build_matrix_haversine_only_when_disabled() -> None:
    coords = [(41.5, 2.2), (41.7, 2.4)]
    # _osrm_matrix should not be called at all when prefer_osrm=False.
    with patch.object(D, "_osrm_matrix") as net:
        m = D.build_matrix(coords, prefer_osrm=False)
    net.assert_not_called()
    assert m.backend == "haversine"


def test_osrm_matrix_parses_response() -> None:
    coords = [(41.5, 2.2), (41.7, 2.4)]
    fake_response = type(
        "R",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: {
                "code": "Ok",
                "distances": [[0, 25_000], [25_000, 0]],
                "durations": [[0, 1800], [1800, 0]],
            },
        },
    )()
    with patch.object(D.requests, "get", return_value=fake_response):
        m = D._osrm_matrix(coords)
    assert m.backend == "osrm"
    assert m.km[0][1] == pytest.approx(25.0)
    assert m.minutes[0][1] == pytest.approx(30.0)
    assert m.km[0][0] == 0.0
