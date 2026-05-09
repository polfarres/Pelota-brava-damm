"""Sanity checks for the ETL output (FR-001 acceptance)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from smart_truck.data import load as L

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"


@pytest.fixture(scope="module")
def parquet_files() -> dict[str, Path]:
    if not PROCESSED.exists():
        pytest.skip(
            "Run `python -m smart_truck.data.load` first to generate parquet files."
        )
    return {p.stem: p for p in PROCESSED.glob("*.parquet")}


def test_all_parquets_present(parquet_files: dict[str, Path]) -> None:
    expected = {"customers", "zones", "products", "time_windows", "deliveries"}
    assert expected.issubset(parquet_files.keys()), parquet_files.keys()


def test_postcodes_are_5_digits() -> None:
    df = L.load_customers()
    bad = df[df["postcode"].str.len().between(1, 4) | (df["postcode"].str.len() > 5)]
    assert bad.empty, f"non-5-digit postcodes: {bad['postcode'].tolist()}"


def test_deliveries_only_dr_routes() -> None:
    df = L.load_deliveries()
    bad = df[~df["route"].astype(str).str.startswith("DR")]
    assert bad.empty, f"non-DR routes leaked: {bad['route'].unique().tolist()}"


def test_time_windows_customer_ids_canonical() -> None:
    df = L.load_time_windows()
    # All canonical IDs are >= 9_000_000_000 (10-digit 9100… range).
    assert (df["customer_id"] >= 9_000_000_000).all()


def test_closed_flag_set_when_window_zero() -> None:
    df = L.load_time_windows()
    same_zero = (df["start_time"].astype(str) == df["end_time"].astype(str)) & (
        df["start_time"].astype(str).str.startswith("00:00")
    )
    assert (df["is_closed"] == same_zero).all()


def test_return_rate_classes() -> None:
    products = L.load_products()
    # BRL barrels should always be 100%.
    barrels = products[products["sku"].astype(str).str.startswith("BRL")]
    if len(barrels):
        assert (barrels["return_rate"] == 1.00).all()
