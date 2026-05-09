"""Unit tests for the geocoder (FR-002)."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from smart_truck.data import geocode as G


def test_build_query_strips_and_appends_country() -> None:
    assert G.build_query("Carrer Major 1", "08100", "MOLLET") == (
        "Carrer Major 1, 08100, MOLLET, Spain"
    )


def test_build_query_skips_missing_parts() -> None:
    assert G.build_query("Carrer Major 1", None, "MOLLET") == (
        "Carrer Major 1, MOLLET, Spain"
    )
    assert G.build_query(float("nan"), "08100", "MOLLET") == "08100, MOLLET, Spain"


def test_geocode_one_uses_cache_hit() -> None:
    cache: dict[str, list[float] | None] = {
        "Carrer Major 1, 08100, MOLLET, Spain": [41.5, 2.2],
    }
    # No HTTP call should happen — patch the network function to assert that.
    with patch.object(G, "_query_address") as net:
        result = G.geocode_one("Carrer Major 1", "08100", "MOLLET", cache)
    assert result == (41.5, 2.2)
    net.assert_not_called()


def test_geocode_one_records_miss_as_none() -> None:
    cache: dict[str, list[float] | None] = {}
    with patch.object(G, "_query_address", return_value=None):
        result = G.geocode_one("Nowhere St", "00000", "Nowhere", cache)
    assert result is None
    # Cache should record the miss as None so we don't retry.
    assert cache["Nowhere St, 00000, Nowhere, Spain"] is None


def test_geocode_one_caches_hit() -> None:
    cache: dict[str, list[float] | None] = {}
    with patch.object(G, "_query_address", return_value=(41.5, 2.2)):
        G.geocode_one("Carrer Major 1", "08100", "MOLLET", cache)
    assert cache["Carrer Major 1, 08100, MOLLET, Spain"] == [41.5, 2.2]


def test_geocode_dataframe_fills_lat_lon() -> None:
    df = pd.DataFrame(
        [
            {"customer_id": 1, "street": "A", "postcode": "00001", "city": "X"},
            {"customer_id": 2, "street": "B", "postcode": "00002", "city": "Y"},
        ]
    )
    cache: dict[str, list[float] | None] = {
        "A, 00001, X, Spain": [41.0, 2.0],
        "B, 00002, Y, Spain": [42.0, 3.0],
    }
    out = G.geocode_dataframe(df, cache=cache, pause_s=0)
    assert list(out["lat"]) == [41.0, 42.0]
    assert list(out["lon"]) == [2.0, 3.0]


def test_geocode_dataframe_handles_misses() -> None:
    df = pd.DataFrame(
        [{"customer_id": 1, "street": "A", "postcode": "00001", "city": "X"}]
    )
    cache: dict[str, list[float] | None] = {"A, 00001, X, Spain": None}
    out = G.geocode_dataframe(df, cache=cache, pause_s=0)
    assert pd.isna(out["lat"].iloc[0])
    assert pd.isna(out["lon"].iloc[0])
