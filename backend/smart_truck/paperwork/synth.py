"""Synthetic Hoja Carga + Hoja Ruta from the deliveries dataset.

For routes that don't have actual DDIDGP source PDFs (everything except
the demo carga DR0027 / 2026-05-08), we still want the Smart Hoja
Carga emitter and the BaselinePlan to work. This module rebuilds
parser.HojaCarga / parser.HojaRuta dataclasses from the per-customer
data in deliveries.parquet so downstream consumers don't have to know
the difference.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .parser import (
    HojaCarga,
    HojaCargaLine,
    HojaCargaTotals,
    HojaRuta,
    HojaRutaStop,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "backend" / "data" / "processed"

# Same UoM normalisation as the optimisation pipeline.
_UOM_NORMALISATION = {
    "CAJ": "Caja",
    "PAK": "Pack",
    "BOT": "Botella",
    "UN": "Unidad",
    "LAT": "Lat",
    "BRL": "Barril",
    "TB": "Tubo",
    "EST": "Caja",       # estoig de promo, comptable com a caixa
    "Caja": "Caja",
    "Pack": "Pack",
    "Botella": "Botella",
    "Unidad": "Unidad",
    "Lat": "Lat",
    "Barril": "Barril",
    "Tubo": "Tubo",
}


def _normalise_uom(uom: str) -> str:
    s = uom.strip()
    if s in _UOM_NORMALISATION:
        return _UOM_NORMALISATION[s]
    return _UOM_NORMALISATION.get(s.upper(), s)


def _fecha_to_dmy(fecha: date) -> str:
    return f"{fecha.day:02d}/{fecha.month:02d}/{fecha.year:04d}"


def _section_for_sku(sku: str, products: pd.DataFrame) -> str:
    """Return the Hoja Carga section a SKU belongs to.

    The deliveries dataset doesn't carry a section field; we infer it
    from products.parquet. Envases (returnable empty containers) are
    flagged ``is_envase=True``; everything else is ``lleno`` (outbound
    full product).
    """
    row = products.loc[products["sku"] == sku]
    if row.empty:
        return "lleno"
    if bool(row.iloc[0]["is_envase"]):
        return "envases"
    return "lleno"


def synthesise_hoja_carga(ruta: str, fecha: date) -> HojaCarga:
    """Build a parser.HojaCarga object from the deliveries parquet.

    Raises :class:`ValueError` when the (ruta, fecha) pair is not in
    the dataset.
    """
    deliveries = pd.read_parquet(PROCESSED_DIR / "deliveries.parquet")
    products = pd.read_parquet(PROCESSED_DIR / "products.parquet")
    df = deliveries[
        (deliveries["route"] == ruta) & (deliveries["date"] == _fecha_to_dmy(fecha))
    ]
    if df.empty:
        raise ValueError(f"No deliveries for ruta={ruta!r} fecha={fecha!r}")

    ubic_map = products.set_index("sku")["warehouse_location"].to_dict()
    desc_map = products.set_index("sku")["description"].to_dict()

    lines: list[HojaCargaLine] = []
    total_units = 0.0
    for _, r in df.iterrows():
        sku = str(r["sku"])
        qty = float(r["quantity"])
        unit = _normalise_uom(str(r["uom"]))
        ubic = ubic_map.get(sku)
        section = _section_for_sku(sku, products)
        lines.append(
            HojaCargaLine(
                section=section,
                ubicacion=str(ubic) if pd.notna(ubic) else None,
                sku=sku,
                description=str(r.get("description") or desc_map.get(sku, "")),
                quantity=qty,
                unit=unit,
                lote=None,
                estado=None,
                descarga=None,
            )
        )
        total_units += qty

    transport_id = int(df["transport_id"].iloc[0]) if pd.notna(df["transport_id"].iloc[0]) else 0
    driver_id = int(df["driver_id"].iloc[0]) if pd.notna(df["driver_id"].iloc[0]) else 0
    return HojaCarga(
        nº_carga=transport_id,
        nº_precarga="",
        vehiculo=str(transport_id),
        repartidor_id=driver_id,
        repartidor_name="",
        nº_viaje=1,
        fecha=fecha,
        ruta=ruta,
        lines=lines,
        totals_entrega=HojaCargaTotals(
            cantidad=int(round(total_units)),
            volumen=None,
            peso_kg=None,
        ),
        totals_devolucion=HojaCargaTotals(cantidad=0, volumen=None, peso_kg=None),
    )


def synthesise_hoja_ruta(ruta: str, fecha: date) -> HojaRuta:
    """Build a parser.HojaRuta object from deliveries + customers.

    The Hoja Ruta is the driver's stop list — one row per customer in
    the order they first appear in the deliveries data. We don't have
    Albarán numbers, payment conditions or proforma totals in the
    deliveries dataset, so we emit reasonable placeholders.
    """
    deliveries = pd.read_parquet(PROCESSED_DIR / "deliveries.parquet")
    customers = pd.read_parquet(PROCESSED_DIR / "customers.parquet")
    df = deliveries[
        (deliveries["route"] == ruta) & (deliveries["date"] == _fecha_to_dmy(fecha))
    ]
    if df.empty:
        raise ValueError(f"No deliveries for ruta={ruta!r} fecha={fecha!r}")

    customers_first = customers.drop_duplicates(subset=["customer_id"], keep="first").set_index(
        "customer_id"
    )

    seen: set[int] = set()
    customer_order: list[int] = []
    for cid in df["customer_id"]:
        cid = int(cid)
        if cid in seen:
            continue
        seen.add(cid)
        customer_order.append(cid)

    stops: list[HojaRutaStop] = []
    for seq, cid in enumerate(customer_order, start=1):
        cust = customers_first.loc[cid] if cid in customers_first.index else None
        name = str(cust["name"]) if cust is not None and pd.notna(cust["name"]) else f"Client {cid}"
        if cust is not None:
            address = f"{cust['street']}, {cust['postcode']} {cust['city']}".strip(", ")
        else:
            address = ""
        stops.append(
            HojaRutaStop(
                sequence=seq,
                sstt="",
                payment_condition="CREDITO",
                albaran_id=cid,
                customer_id=cid,
                customer_name=name,
                address=address,
                proforma_total=Decimal("0"),
                cash_total=Decimal("0"),
            )
        )

    transport_id = int(df["transport_id"].iloc[0]) if pd.notna(df["transport_id"].iloc[0]) else 0
    driver_id = int(df["driver_id"].iloc[0]) if pd.notna(df["driver_id"].iloc[0]) else 0
    return HojaRuta(
        nº_carga=transport_id,
        fecha=fecha,
        vehiculo=str(transport_id),
        repartidor_id=driver_id,
        repartidor_name="",
        preparador=None,
        nº_viaje=1,
        stops=stops,
        total_carga=None,
        total_cobro=None,
    )
