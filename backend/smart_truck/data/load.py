"""ETL: read raw xlsx files into clean parquet (FR-001).

Inputs: ``Hackaton/DAMM/{Hackaton.xlsx, Horarios Entrega.XLSX, ZM040.XLSX}``.
Outputs (in ``backend/data/processed/``):

- ``customers.parquet``     - DR-001.C
- ``zones.parquet``         - DR-001.D
- ``products.parquet``      - DR-001.E + DR-003 (collapsed)
- ``time_windows.parquet``  - DR-002 (only canonical 9100... IDs)
- ``deliveries.parquet``    - DR-001.A (legacy ``DA...`` route filtered out)

Run::

    python -m smart_truck.data.load
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "Hackaton" / "DAMM"
DATA_DIR = REPO_ROOT / "backend" / "data" / "processed"

FILE_HACKATON = RAW_DIR / "Hackaton.xlsx"
FILE_HORARIOS = RAW_DIR / "Horarios Entrega.XLSX"
FILE_ZM040 = RAW_DIR / "ZM040.XLSX"


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


def _return_rate(sku: object, description: object) -> float:
    """A-07: BRL=100% RET=80% SR=0% other=60%."""
    s = str(sku).upper() if pd.notna(sku) else ""
    d = str(description).upper() if pd.notna(description) else ""
    if s.startswith("BRL"):
        return 1.00
    if " SR" in f" {d}" or s.endswith("SR"):
        return 0.00
    if "RET" in d:
        return 0.80
    return 0.60


def load_products() -> pd.DataFrame:
    zubic = _load_materials_zubic()
    zm = _load_zm040()
    flat = _collapse_zm040(zm)
    products = zubic.merge(flat, on="sku", how="left")
    products["is_envase"] = products["sku"].apply(_is_envase)
    products["is_returnable"] = products["description"].apply(_is_returnable)
    products["return_rate"] = products.apply(
        lambda r: _return_rate(r["sku"], r["description"]), axis=1
    )
    return products


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

    print("Loading products (Materiales zubic + ZM040)...")
    products = load_products()
    products.to_parquet(DATA_DIR / "products.parquet", index=False)
    print(f"  {len(products):,} products")

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
