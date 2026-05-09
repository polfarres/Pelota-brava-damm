"""ETL: read raw xlsx files into clean parquet (FR-001).

Inputs: ``Hackaton/DAMM/{Hackaton.xlsx, Horarios Entrega.XLSX, ZM040.XLSX,
Caixes_Estadístiques.xlsx}``.
Outputs (in ``backend/data/processed/``):

- ``customers.parquet``     - DR-001.C
- ``zones.parquet``         - DR-001.D
- ``products.parquet``      - DR-001.E + DR-003 (collapsed) + DR-010 ce_per_unit
- ``time_windows.parquet``  - DR-002 (only canonical 9100... IDs)
- ``deliveries.parquet``    - DR-001.A (legacy ``DA...`` route filtered out)
- ``ce_coverage.json``      - DR-010 source breakdown per SKU

Run::

    python -m smart_truck.data.load
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "Hackaton" / "DAMM"
DATA_DIR = REPO_ROOT / "backend" / "data" / "processed"
CE_OVERRIDES_FILE = REPO_ROOT / "backend" / "smart_truck" / "data" / "ce_overrides.yaml"

FILE_HACKATON = RAW_DIR / "Hackaton.xlsx"
FILE_HORARIOS = RAW_DIR / "Horarios Entrega.XLSX"
FILE_ZM040 = RAW_DIR / "ZM040.XLSX"
FILE_CE_MASTER = RAW_DIR / "Caixes_Estadístiques.xlsx"


def normalise_postcode(cp: object) -> str:
    if pd.isna(cp):
        return ""
    try:
        return f"{int(cp):05d}"
    except (TypeError, ValueError):
        return str(cp).strip()


# ---------------------------------------------------------------------------
# Customer master (DR-001.C)
# ---------------------------------------------------------------------------


def load_customers() -> pd.DataFrame:
    df = pd.read_excel(FILE_HACKATON, sheet_name="Direcciones")
    df = df.rename(
        columns={
            "Cliente": "customer_id",
            "Nombre 1": "name1",
            "Nombre 2": "name2",
            "Calle": "street",
            "CP": "postcode",
            "Población": "city",
        }
    )
    df["postcode"] = df["postcode"].apply(normalise_postcode)
    df["name"] = df.apply(
        lambda r: " ".join(
            str(v).strip() for v in (r.get("name1"), r.get("name2")) if pd.notna(v)
        ),
        axis=1,
    )
    return df[["customer_id", "name", "street", "postcode", "city"]]


# ---------------------------------------------------------------------------
# Delivery zones (DR-001.D)
# ---------------------------------------------------------------------------


def load_zones() -> pd.DataFrame:
    df = pd.read_excel(FILE_HACKATON, sheet_name="ZONAS")
    return df


# ---------------------------------------------------------------------------
# Products (DR-001.E + DR-003)
# ---------------------------------------------------------------------------


def _load_materials_zubic() -> pd.DataFrame:
    df = pd.read_excel(FILE_HACKATON, sheet_name="Materiales zubic")
    df = df.rename(
        columns={
            "Material": "sku",
            "Número de material": "description",
            "UMB": "base_uom",
            "Ubic.": "warehouse_location",
        }
    )
    return df[["sku", "description", "base_uom", "warehouse_location"]]


def _load_zm040() -> pd.DataFrame:
    df = pd.read_excel(FILE_ZM040, sheet_name="Sheet1")
    df = df.rename(
        columns={
            "Material": "sku",
            "UMA": "uom",
            "Longitud": "length_cm",
            "Ancho": "width_cm",
            "Altura": "height_cm",
            "Volumen": "volume",
            "Peso bruto": "gross_weight_kg",
            "Peso neto": "net_weight_kg",
            "Código EAN/UPC": "ean",
        }
    )
    return df


def _collapse_zm040(zm: pd.DataFrame) -> pd.DataFrame:
    """For each SKU, pick the case (CAJ) and pallet (PAL) row to flatten dims."""
    case_cols = {
        "length_cm": "case_length_cm",
        "width_cm": "case_width_cm",
        "height_cm": "case_height_cm",
        "volume": "case_volume",
        "gross_weight_kg": "case_weight_kg",
    }
    pallet_cols = {
        "length_cm": "pallet_length_cm",
        "width_cm": "pallet_width_cm",
        "height_cm": "pallet_height_cm",
        "volume": "pallet_volume",
        "gross_weight_kg": "pallet_weight_kg",
    }

    case = (
        zm[zm["uom"] == "CAJ"]
        .drop_duplicates("sku", keep="first")
        .rename(columns=case_cols)[["sku", *case_cols.values(), "ean"]]
    )
    pallet = (
        zm[zm["uom"] == "PAL"]
        .drop_duplicates("sku", keep="first")
        .rename(columns=pallet_cols)[["sku", *pallet_cols.values()]]
    )
    return case.merge(pallet, on="sku", how="outer")


def _is_envase(sku: object) -> bool:
    if pd.isna(sku):
        return False
    s = str(sku)
    return (
        s.startswith("3ENV")
        or s.startswith("CJ")
        or (s.startswith("BRL") and s.endswith("V"))
        or s == "TB8V"
    )


def _is_returnable(description: object) -> bool:
    if pd.isna(description):
        return False
    return "RET" in str(description).upper()


# A-35 supersedes the per-class A-07 rates with a flat 60 % global.
RETURN_RATE_FLAT = 0.60


def _load_ce_overrides() -> dict[str, float]:
    if not CE_OVERRIDES_FILE.exists():
        return {}
    with CE_OVERRIDES_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {str(k): float(v) for k, v in data.items()}


def _load_ce_master() -> dict[str, float]:
    """Authoritative SKU → CE per delivery unit from the mentor-supplied file.

    Returns empty dict when the file is missing — callers fall back to ZM040.
    The file's column names aren't fixed yet; we accept any header whose
    name matches one of the known synonyms (case-insensitive).
    """
    if not FILE_CE_MASTER.exists():
        return {}
    df = pd.read_excel(FILE_CE_MASTER)
    sku_col = _first_match(df.columns, ("material", "sku", "código", "codigo"))
    ce_col = _first_match(df.columns, ("ce", "caixes", "estadistic", "estadístic"))
    if sku_col is None or ce_col is None:
        return {}
    out: dict[str, float] = {}
    for sku, ce in zip(df[sku_col], df[ce_col]):
        if pd.isna(sku) or pd.isna(ce):
            continue
        try:
            out[str(sku).strip()] = float(ce)
        except (TypeError, ValueError):
            continue
    return out


def _first_match(cols, needles: tuple[str, ...]) -> str | None:
    for c in cols:
        cl = str(c).lower()
        if any(n in cl for n in needles):
            return c
    return None


def _ce_from_zm040(zm: pd.DataFrame) -> dict[str, float]:
    """ZM040 fallback: CE = ZCE_row.Denominator / 100."""
    zce = zm[zm["uom"] == "ZCE"][["sku", "Denom."]].copy() if "Denom." in zm.columns else None
    if zce is None or zce.empty:
        return {}
    zce = zce.rename(columns={"Denom.": "denom"}).dropna(subset=["denom"])
    zce = zce.drop_duplicates("sku", keep="first")
    return {str(r["sku"]): float(r["denom"]) / 100.0 for _, r in zce.iterrows()}


def resolve_ce_per_unit(
    sku: str,
    overrides: dict[str, float],
    ce_master: dict[str, float],
    ce_zm040: dict[str, float],
) -> tuple[float, str]:
    """DR-010 source priority: OVERRIDE > CE_MASTER > ZCE_ROW > DEFAULT (=1.0)."""
    if sku in overrides:
        return overrides[sku], "OVERRIDE"
    if sku in ce_master:
        return ce_master[sku], "CE_MASTER"
    if sku in ce_zm040:
        return ce_zm040[sku], "ZCE_ROW"
    return 1.0, "DEFAULT"


def load_products() -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Returns (products_df, ce_coverage) — coverage maps source → SKU list."""
    zubic = _load_materials_zubic()
    zm = _load_zm040()
    flat = _collapse_zm040(zm)
    products = zubic.merge(flat, on="sku", how="left")
    products["is_envase"] = products["sku"].apply(_is_envase)
    products["is_returnable"] = products["description"].apply(_is_returnable)
    products["return_rate"] = RETURN_RATE_FLAT  # A-35

    overrides = _load_ce_overrides()
    ce_master = _load_ce_master()
    ce_zm040 = _ce_from_zm040(zm)
    ce_results = products["sku"].apply(
        lambda s: resolve_ce_per_unit(str(s), overrides, ce_master, ce_zm040)
    )
    products["ce_per_unit"] = [r[0] for r in ce_results]
    products["ce_source"] = [r[1] for r in ce_results]

    coverage: dict[str, list[str]] = {"OVERRIDE": [], "CE_MASTER": [], "ZCE_ROW": [], "DEFAULT": []}
    for sku, src in zip(products["sku"], products["ce_source"]):
        coverage[src].append(str(sku))
    return products, coverage


# ---------------------------------------------------------------------------
# Time windows (DR-002)
# ---------------------------------------------------------------------------


def _time_to_hhmmss(value: object) -> str:
    """Normalise Excel time cells to ``HH:MM:SS`` strings.

    pandas reads time-only Excel cells as :class:`datetime.timedelta` (offset
    from midnight). pyarrow can't serialise timedeltas to parquet; strings
    keep the ``00:00:00`` sentinel intact and round-trip cleanly.
    """
    import datetime as dt

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, dt.timedelta):
        total = int(value.total_seconds())
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    if isinstance(value, dt.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, dt.datetime):
        return value.strftime("%H:%M:%S")
    return str(value).strip()


def load_time_windows() -> pd.DataFrame:
    df = pd.read_excel(FILE_HORARIOS, sheet_name="Sheet1")
    df = df.rename(
        columns={
            "Deudor": "customer_id",
            "Día semana": "weekday",
            "Horario inicia a": "start_time",
            "Horario termina a": "end_time",
        }
    )
    df["customer_id"] = pd.to_numeric(df["customer_id"], errors="coerce")
    # Drop the small handful of legacy 6-digit IDs; keep canonical 9100... 10-digit IDs.
    df = df[df["customer_id"] >= 9_000_000_000]
    df["customer_id"] = df["customer_id"].astype("int64")
    # Normalise time cells to HH:MM:SS strings (parquet-safe).
    df["start_time"] = df["start_time"].apply(_time_to_hhmmss)
    df["end_time"] = df["end_time"].apply(_time_to_hhmmss)
    # K = L = 00:00:00 means closed that weekday.
    df["is_closed"] = (df["start_time"] == df["end_time"]) & (
        df["start_time"] == "00:00:00"
    )
    return df[["customer_id", "weekday", "start_time", "end_time", "is_closed"]]


# ---------------------------------------------------------------------------
# Deliveries fact table (DR-001.A)
# ---------------------------------------------------------------------------


def load_deliveries() -> pd.DataFrame:
    df = pd.read_excel(FILE_HACKATON, sheet_name="Detalle entrega")
    df = df.rename(
        columns={
            "FECHA": "date",
            "Transporte": "transport_id",
            "Ruta": "route",
            "Repartidor": "driver_id",
            "Entrega": "delivery_id",
            "Material": "sku",
            "Denominación": "description",
            "Cantidad entrega": "quantity",
            "Un.medida venta": "uom",
            "Calle": "street",
            "CP": "postcode",
            "Población": "city",
            "ZonaTransp": "zone_code",
        }
    )
    # The customer ID column has a duplicate-ish name; pick the one suffixed with .1.
    customer_cols = [c for c in df.columns if "Destinatario" in str(c) and ".1" in str(c)]
    if customer_cols:
        df = df.rename(columns={customer_cols[0]: "customer_id"})
    df = df[df["route"].astype(str).str.startswith("DR")]
    df["postcode"] = df["postcode"].apply(normalise_postcode)
    # Coerce string-ish columns that arrive with mixed types (some rows int,
    # some str) so parquet serialisation is happy.
    for col in ("route", "sku", "uom", "street", "city", "zone_code", "description"):
        if col in df.columns:
            df[col] = df[col].astype("string").fillna("")
    keep = [
        "date",
        "transport_id",
        "route",
        "driver_id",
        "delivery_id",
        "customer_id",
        "sku",
        "description",
        "quantity",
        "uom",
        "street",
        "postcode",
        "city",
        "zone_code",
    ]
    return df[[c for c in keep if c in df.columns]]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {DATA_DIR}")

    print("Loading customers...")
    customers = load_customers()
    customers.to_parquet(DATA_DIR / "customers.parquet", index=False)
    print(f"  {len(customers):,} customers")

    print("Loading zones...")
    zones = load_zones()
    zones.to_parquet(DATA_DIR / "zones.parquet", index=False)
    print(f"  {len(zones):,} zone rows")

    print("Loading products (Materiales zubic + ZM040 + CE master)...")
    products, ce_coverage = load_products()
    products.to_parquet(DATA_DIR / "products.parquet", index=False)
    with (DATA_DIR / "ce_coverage.json").open("w", encoding="utf-8") as f:
        json.dump({k: sorted(set(v)) for k, v in ce_coverage.items()}, f, indent=2)
    summary = {k: len(set(v)) for k, v in ce_coverage.items()}
    print(f"  {len(products):,} products | CE source breakdown: {summary}")

    print("Loading time windows...")
    tw = load_time_windows()
    tw.to_parquet(DATA_DIR / "time_windows.parquet", index=False)
    n_customers = tw["customer_id"].nunique()
    n_closed = int(tw["is_closed"].sum())
    print(
        f"  {len(tw):,} time-window rows ({n_customers} customers; {n_closed} closed-day rows)"
    )

    print("Loading deliveries...")
    deliveries = load_deliveries()
    deliveries.to_parquet(DATA_DIR / "deliveries.parquet", index=False)
    print(f"  {len(deliveries):,} delivery line items")

    print("ETL complete.")


if __name__ == "__main__":
    main()
