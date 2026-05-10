"""Baseline plan reconstruction (FR-004).

Reads the source DDIDGP paperwork (``Hoja Carga`` + ``Hoja Ruta``) for a
carga and rebuilds the as-is operation as a :class:`BaselinePlan`,
ready to feed the KPI engine (FR-009).

What the baseline captures:

- Stop sequence — the printed ``Hoja Ruta`` order (A-04: drivers don't
  re-sequence on the road because the load is built around it).
- Stop-level metadata enriched from the data layer: lat/lon from
  ``customers.parquet`` (geocoded), per-weekday time window from
  ``time_windows.parquet``, payment condition + proforma total from the
  Hoja Ruta itself.
- Slot assignments — one logical slot per distinct ``Ubicación`` in the
  Hoja Carga (mirrors how the picker walks the warehouse), plus an
  envase slot when the carga has any.
- ``in_truck_zones_touched`` per stop — estimated from
  ``ceil(total_delivery_lines / num_stops)`` because we lack the
  per-customer Albarán PDFs needed to attribute lines to stops; the KPI
  engine knows how to interpret this aggregate. Reserved for v2:
  Albarán parsing for exact per-stop attribution.

What the baseline deliberately omits:

- ``delivered_lines`` per stop — same reason as above.
- ETA per stop — the baseline doesn't simulate the route; the KPI
  engine derives total time directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

import pandas as pd

from .models import (
    BaselinePlan,
    DeliveredLine,
    PaymentCondition,
    SlotAssignment,
    StopPlan,
    VehicleProfileName,
)
from .paperwork.parser import (
    HojaCarga,
    HojaCargaLine,
    HojaRuta,
    parse_hoja_carga,
    parse_hoja_ruta,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "backend" / "data" / "processed"
RECURSOS_DIR = REPO_ROOT / "Hackaton" / "DAMM" / "RECURSOS"

# Until we wire fleet metadata, default the demo route's vehicle to a
# six-pallet side-curtain truck (the most common DDI Mollet profile).
DEFAULT_VEHICLE_PROFILE: VehicleProfileName = "truck_6p_sidecurtain"


@dataclass
class BaselineInputs:
    """The data-layer dataframes the reconstruction needs."""

    customers: pd.DataFrame  # has lat / lon when geocoded
    time_windows: pd.DataFrame  # canonical 9100… IDs + weekday + start/end
    products: pd.DataFrame  # has ce_per_unit, weight_kg, return_rate

    @classmethod
    def load(cls) -> BaselineInputs:
        return cls(
            customers=pd.read_parquet(DATA_DIR / "customers.parquet"),
            time_windows=pd.read_parquet(DATA_DIR / "time_windows.parquet"),
            products=pd.read_parquet(DATA_DIR / "products.parquet"),
        )


def reconstruct_baseline(
    carga_pdf: Path,
    ruta_pdf: Path,
    inputs: BaselineInputs | None = None,
    vehicle_profile: VehicleProfileName = DEFAULT_VEHICLE_PROFILE,
) -> BaselinePlan:
    """Read the paperwork PDFs and build a :class:`BaselinePlan`."""
    if inputs is None:
        inputs = BaselineInputs.load()

    hc = parse_hoja_carga(carga_pdf)
    hr = parse_hoja_ruta(ruta_pdf)

    if hc.nº_carga != hr.nº_carga:
        raise ValueError(
            f"Hoja Carga / Hoja Ruta carga IDs disagree: {hc.nº_carga} vs {hr.nº_carga}"
        )

    stops = _build_stops(hr, hc, inputs)
    slots = _build_baseline_slots(hc, inputs)

    return BaselinePlan(
        ruta=hc.ruta,
        fecha=hc.fecha,
        vehicle_profile=vehicle_profile,
        stops=stops,
        slot_assignments=slots,
    )


def reconstruct_baseline_from_synth(
    hc: HojaCarga,
    hr: HojaRuta,
    inputs: BaselineInputs | None = None,
    vehicle_profile: VehicleProfileName = DEFAULT_VEHICLE_PROFILE,
) -> BaselinePlan:
    """Same as :func:`reconstruct_baseline` but takes already-built
    :class:`HojaCarga` / :class:`HojaRuta` objects (synthesised from
    deliveries.parquet for routes that don't have source PDFs).
    """
    if inputs is None:
        inputs = BaselineInputs.load()

    stops = _build_stops(hr, hc, inputs)
    slots = _build_baseline_slots(hc, inputs)

    return BaselinePlan(
        ruta=hc.ruta,
        fecha=hc.fecha,
        vehicle_profile=vehicle_profile,
        stops=stops,
        slot_assignments=slots,
    )


# ---------------------------------------------------------------------------
# Stops
# ---------------------------------------------------------------------------


def _build_stops(
    hr: HojaRuta,
    hc: HojaCarga,
    inputs: BaselineInputs,
) -> list[StopPlan]:
    """Convert Hoja Ruta rows into :class:`StopPlan` objects enriched
    with lat/lon and time windows from the parquet tables.
    """
    weekday = hr.fecha.isoweekday()

    customers_first = (
        inputs.customers.drop_duplicates(subset=["customer_id"], keep="first").set_index(
            "customer_id"
        )
    )
    tw_today = inputs.time_windows[inputs.time_windows["weekday"] == weekday]
    tw_first = tw_today.drop_duplicates(subset=["customer_id"], keep="first").set_index(
        "customer_id"
    )

    avg_zones = _estimate_zones_touched_per_stop(hc, len(hr.stops))

    stops: list[StopPlan] = []
    for raw_stop in hr.stops:
        cust = customers_first.loc[raw_stop.customer_id] if raw_stop.customer_id in customers_first.index else None
        lat = lon = None
        address = raw_stop.address
        if cust is not None:
            lat = float(cust["lat"]) if pd.notna(cust.get("lat")) else None
            lon = float(cust["lon"]) if pd.notna(cust.get("lon")) else None
            address = f"{cust['street']}, {cust['postcode']} {cust['city']}".strip(", ")

        time_window: tuple[time, time] | None = None
        if raw_stop.customer_id in tw_first.index:
            tw_row = tw_first.loc[raw_stop.customer_id]
            if not bool(tw_row["is_closed"]):
                time_window = (
                    _parse_time(tw_row["start_time"]),
                    _parse_time(tw_row["end_time"]),
                )

        stops.append(
            StopPlan(
                sequence=raw_stop.sequence,
                customer_id=raw_stop.customer_id,
                customer_name=raw_stop.customer_name,
                address=address,
                lat=lat,
                lon=lon,
                eta=None,  # baseline doesn't simulate timing per stop.
                time_window=time_window,
                payment_condition=raw_stop.payment_condition,
                proforma_total=raw_stop.proforma_total,
                delivered_lines=[],
                returns_estimated_ce=0.0,
                in_truck_zones_touched=avg_zones,
            )
        )
    return stops


def _estimate_zones_touched_per_stop(hc: HojaCarga, num_stops: int) -> int:
    """Average distinct warehouse Ubicaciones a driver hits per stop in
    a load-by-Ubicación baseline.

    Approximated as ``ceil(num_outbound_lines / num_stops)``: outbound
    lines (``lleno`` + ``lleno_sin_ubic``) are spread across the route;
    in the worst case each line forces one access, so this is a defensible
    upper-ish bound for the baseline. The Smart packer reduces this to
    1 per stop (each customer's items are clustered).
    """
    if num_stops <= 0:
        return 0
    outbound = sum(
        1 for ln in hc.lines if ln.section in ("lleno", "lleno_sin_ubic")
    )
    return max(1, math.ceil(outbound / num_stops))


def _parse_time(s: object) -> time:
    """``"HH:MM:SS"`` → :class:`datetime.time`."""
    text = str(s)
    parts = text.split(":")
    h, m = int(parts[0]), int(parts[1])
    sec = int(parts[2]) if len(parts) > 2 else 0
    return time(h, m, sec)


# ---------------------------------------------------------------------------
# Slot assignments — load-by-Ubicación lex sort
# ---------------------------------------------------------------------------


def _build_baseline_slots(hc: HojaCarga, inputs: BaselineInputs) -> list[SlotAssignment]:
    """In the baseline the truck is loaded the way the picker walks the
    warehouse: by ``Ubicación`` in lex order. We materialise one logical
    slot per distinct ``Ubicación`` for outbound items, plus a single
    ``envases`` slot if the carga ships any.

    These don't map 1:1 onto the truck's physical pallet positions —
    that's by design: the baseline pre-dates the hybrid load model. The
    frontend's "Original (DDIDGP)" view of the Smart Hoja Carga renders
    these slots' ``contents`` directly so the picker can see the as-is
    paperwork side-by-side with the Smart version.
    """
    ce_per_unit = (
        inputs.products.set_index("sku")["ce_per_unit"].to_dict()
        if "ce_per_unit" in inputs.products.columns
        else {}
    )

    def _to_delivered(ln: HojaCargaLine) -> DeliveredLine:
        return DeliveredLine(
            sku=ln.sku,
            description=ln.description,
            quantity=ln.quantity,
            unit=ln.unit,
            ce=float(ce_per_unit.get(ln.sku, 1.0)),
            weight_kg=0.0,
            source_ubicacion=ln.ubicacion,
        )

    by_ubic: dict[str, list[HojaCargaLine]] = {}
    envase_lines: list[HojaCargaLine] = []

    for ln in hc.lines:
        if ln.section == "envases":
            envase_lines.append(ln)
            continue
        if ln.section == "retorno":
            # Carga retorno is supplier returns, not customer-facing —
            # skip from the baseline truck-load model.
            continue
        key = ln.ubicacion or "(no_ubic)"
        by_ubic.setdefault(key, []).append(ln)

    slots: list[SlotAssignment] = []
    for ubic in sorted(by_ubic):
        contents = [_to_delivered(ln) for ln in by_ubic[ubic]]
        ce_used = sum(c.ce * c.quantity for c in contents)
        slots.append(
            SlotAssignment(
                slot_id=f"baseline-{ubic}",
                is_envase_zone=False,
                stop_sequences=[],  # no per-stop attribution available in v1
                contents=contents,
                ce_used=ce_used,
            )
        )
    if envase_lines:
        contents = [_to_delivered(ln) for ln in envase_lines]
        ce_used = sum(c.ce * c.quantity for c in contents)
        slots.append(
            SlotAssignment(
                slot_id="baseline-envases",
                is_envase_zone=True,
                stop_sequences=[],
                contents=contents,
                ce_used=ce_used,
            )
        )
    return slots
