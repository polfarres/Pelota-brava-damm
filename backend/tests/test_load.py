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


def test_return_rate_flat_60_pct_a35() -> None:
    products, _ = L.load_products()
    assert (products["return_rate"] == L.RETURN_RATE_FLAT).all()
    assert L.RETURN_RATE_FLAT == 0.60


def test_ce_per_unit_source_priority_dr010() -> None:
    overrides = {"FAKE_OVERRIDE": 7.0}
    ce_master = {"FAKE_MASTER": 2.5, "FAKE_OVERRIDE": 99.0}
    ce_zm040 = {"FAKE_ZCE": 1.5, "FAKE_MASTER": 99.0}

    assert L.resolve_ce_per_unit("FAKE_OVERRIDE", overrides, ce_master, ce_zm040) == (7.0, "OVERRIDE")
    assert L.resolve_ce_per_unit("FAKE_MASTER", overrides, ce_master, ce_zm040) == (2.5, "CE_MASTER")
    assert L.resolve_ce_per_unit("FAKE_ZCE", overrides, ce_master, ce_zm040) == (1.5, "ZCE_ROW")
    assert L.resolve_ce_per_unit("UNKNOWN", overrides, ce_master, ce_zm040) == (1.0, "DEFAULT")


def test_ce_per_unit_column_present() -> None:
    products, coverage = L.load_products()
    assert "ce_per_unit" in products.columns
    assert "ce_source" in products.columns
    assert (products["ce_per_unit"] > 0).all()
    assert set(coverage) == {"OVERRIDE", "CE_MASTER", "ZCE_ROW", "DEFAULT"}
