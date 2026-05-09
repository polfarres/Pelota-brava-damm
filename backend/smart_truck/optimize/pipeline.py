"""FR-008: orchestrator. Joint route + load + returns optimisation.

Public entry point: :func:`plan`. Reads the day's parquet datasets,
derives the stop list and per-stop demand, then runs:

route → load → returns

If returns is infeasible, we re-run route once with a more conservative
familiarity weight (mimicking the as-is order, which the dispatcher
already vetted by hand). If it still fails, we surface the error so
the caller can downsize the carga.

For ``ruta="DR0027"`` and ``fecha=2026-05-08`` we cross-reference the
parsed Hoja Carga PDF (the actual demo carga) for the per-stop SKU list
when the parquet doesn't have that exact day. This is the demo path.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from smart_truck.domain.vehicle_loader import VEHICLES_DIR, load_profile
from smart_truck.models import (
    DeliveredLine,
    Explanation,
    Plan,
    SlotAssignment,
    StopPlan,
    VehicleProfileName,
)
from smart_truck.optimize.load import (
    StopDemand,
    pack_truck,
)
from smart_truck.optimize.returns import (
    ReturnsInfeasibleError,
    estimate_returnable_ce_per_stop,
    simulate_returns,
)
from smart_truck.optimize.route import RouteStop, solve_route


REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "backend" / "data" / "processed"
HOJA_CARGA_PDF = REPO_ROOT / "Hackaton" / "DAMM" / "RECURSOS" / "Hoja Carga.pdf"
HOJA_RUTA_PDF = REPO_ROOT / "Hackaton" / "DAMM" / "RECURSOS" / "Hoja Ruta.pdf"

# Mollet del Vallès depot (used for DAMM Distribució). Approximate.
DEPOT_LAT_LON: tuple[float, float] = (41.5396, 2.2103)


# ---------------------------------------------------------------------------
# Profile lookup
# ---------------------------------------------------------------------------

_PROFILE_TO_FILE = {
    "furgo_3p": "furgo_3p.yaml",
    "truck_6p_sidecurtain": "truck_6p_sidecurtain.yaml",
    "truck_8p_sidecurtain": "truck_8p_sidecurtain.yaml",
    "truck_8p_lift": "truck_8p_lift.yaml",
}


def _load_vehicle(profile_name: str):
    fname = _PROFILE_TO_FILE.get(profile_name)
    if not fname:
        raise ValueError(f"Unknown vehicle profile: {profile_name!r}")
    return load_profile(VEHICLES_DIR / fname)


# ---------------------------------------------------------------------------
# Data wiring
# ---------------------------------------------------------------------------


def _normalise_date(d: date | str) -> str:
    """Parquet stores dates as ``dd/mm/yyyy`` strings; accept either form."""
    if isinstance(d, str):
        return d
    return d.strftime("%d/%m/%Y")


def _ce_per_unit_map() -> dict[str, float]:
    products = pd.read_parquet(PROCESSED_DIR / "products.parquet")
    return {str(r["sku"]): float(r["ce_per_unit"]) for _, r in products.iterrows()}


def _is_returnable_map() -> dict[str, bool]:
    products = pd.read_parquet(PROCESSED_DIR / "products.parquet")
    return {str(r["sku"]): bool(r["is_returnable"]) for _, r in products.iterrows()}


def _is_envase_map() -> dict[str, bool]:
    products = pd.read_parquet(PROCESSED_DIR / "products.parquet")
    return {str(r["sku"]): bool(r["is_envase"]) for _, r in products.iterrows()}


def _customers_geo() -> dict[int, tuple[str, str, float | None, float | None]]:
    customers = pd.read_parquet(PROCESSED_DIR / "customers.parquet")
    out: dict[int, tuple[str, str, float | None, float | None]] = {}
    for _, r in customers.iterrows():
        out[int(r["customer_id"])] = (
            str(r["name"]),
            f"{r['street']} {r['postcode']} {r['city']}".strip(),
            float(r["lat"]) if pd.notna(r["lat"]) else None,
            float(r["lon"]) if pd.notna(r["lon"]) else None,
        )
    return out


def _description_map() -> dict[str, str]:
    products = pd.read_parquet(PROCESSED_DIR / "products.parquet")
    return {str(r["sku"]): str(r["description"]) for _, r in products.iterrows()}


def _build_stop_demands_from_deliveries(
    ruta: str, fecha: date
) -> tuple[list[StopDemand], dict[int, str]]:
    """Read ``deliveries.parquet`` and return the per-customer demand
    list for that route+date. ``stop sequence`` follows the order
    customers first appear in the file.
    """
    deliveries = pd.read_parquet(PROCESSED_DIR / "deliveries.parquet")
    fecha_str = _normalise_date(fecha)
    df = deliveries[
        (deliveries["route"] == ruta) & (deliveries["date"] == fecha_str)
    ]
    if df.empty:
        return [], {}

    ce_map = _ce_per_unit_map()
    desc_map = _description_map()

    # Group by customer in order of first appearance.
    customer_order: list[int] = []
    seen = set()
    for cid in df["customer_id"]:
        cid = int(cid)
        if cid not in seen:
            customer_order.append(cid)
            seen.add(cid)

    stops: list[StopDemand] = []
    cust_to_albaran: dict[int, str] = {}
    for seq, cid in enumerate(customer_order, start=1):
        sub = df[df["customer_id"] == cid]
        lines: list[DeliveredLine] = []
        for _, r in sub.iterrows():
            sku = str(r["sku"])
            qty = float(r["quantity"])
            ce = ce_map.get(sku, 1.0)
            lines.append(
                DeliveredLine(
                    sku=sku,
                    description=desc_map.get(sku, str(r.get("description", ""))),
                    quantity=qty,
                    unit=str(r.get("uom", "Caja")),
                    ce=ce,
                    weight_kg=0.0,
                    source_ubicacion=None,
                )
            )
        stops.append(StopDemand(sequence=seq, customer_id=cid, lines=lines))
    return stops, cust_to_albaran


def _build_stop_demands_from_paperwork(
    ruta: str, fecha: date
) -> tuple[list[StopDemand], list[Any]]:
    """Use the parsed Hoja Carga + Hoja Ruta PDFs as the demand source.

    Hoja Ruta gives us the customer order. Hoja Carga gives us SKU lines
    aggregated for the whole truck (no per-customer split). We allocate
    each SKU line proportionally across stops by their proforma totals.

    Returns (stops, hoja_ruta_stops). Used for the demo carga only when
    the parquet doesn't have data for that day.
    """
    from smart_truck.paperwork.parser import parse_hoja_carga, parse_hoja_ruta

    if not HOJA_CARGA_PDF.exists() or not HOJA_RUTA_PDF.exists():
        return [], []

    hc = parse_hoja_carga(HOJA_CARGA_PDF)
    hr = parse_hoja_ruta(HOJA_RUTA_PDF)
    if hc.ruta != ruta or hr.fecha != fecha:
        # Different demo paperwork; bail.
        if hc.ruta != ruta or hc.fecha != fecha:
            return [], []

    ce_map = _ce_per_unit_map()
    desc_map = _description_map()

    # Dedup stops by customer_id, preserving order of first appearance.
    seen: set[int] = set()
    ordered_customers: list[Any] = []
    for s in hr.stops:
        if s.customer_id in seen:
            continue
        seen.add(s.customer_id)
        ordered_customers.append(s)

    if not ordered_customers:
        return [], []

    # Aggregate Hoja Carga lines by SKU (across "lleno" sections).
    agg: dict[str, dict[str, Any]] = {}
    for ln in hc.lines:
        if ln.section in ("envases", "retorno"):
            continue
        sku = ln.sku
        ce_per = ce_map.get(sku, 1.0)
        existing = agg.get(sku)
        if existing is None:
            agg[sku] = {
                "sku": sku,
                "description": desc_map.get(sku, ln.description),
                "quantity": ln.quantity,
                "unit": ln.unit,
                "ce": ce_per,
                "ubicacion": ln.ubicacion,
            }
        else:
            existing["quantity"] += ln.quantity

    # Allocate quantities proportionally across customers by their
    # proforma totals (positive only — abonos/credit-notes don't pull
    # full pallets). If totals are degenerate, split evenly.
    weights = []
    for s in ordered_customers:
        w = float(s.proforma_total) if s.proforma_total > 0 else 0.0
        weights.append(w)
    total_w = sum(weights)
    if total_w <= 0:
        weights = [1.0] * len(ordered_customers)
        total_w = float(len(ordered_customers))

    # Build stops. Allocate each SKU's quantity proportional to weights.
    stops: list[StopDemand] = []
    for i, customer in enumerate(ordered_customers):
        share = weights[i] / total_w
        lines: list[DeliveredLine] = []
        for sku, info in agg.items():
            qty = info["quantity"] * share
            if qty < 1e-3:
                continue
            lines.append(
                DeliveredLine(
                    sku=sku,
                    description=info["description"],
                    quantity=qty,
                    unit=info["unit"],
                    ce=info["ce"],
                    weight_kg=0.0,
                    source_ubicacion=info["ubicacion"],
                )
            )
        stops.append(
            StopDemand(
                sequence=i + 1,
                customer_id=customer.customer_id,
                lines=lines,
            )
        )

    return stops, ordered_customers


def _envase_lines_from_paperwork() -> list[DeliveredLine]:
    """Outbound envases declared in the Hoja Carga ``envases`` section."""
    if not HOJA_CARGA_PDF.exists():
        return []
    from smart_truck.paperwork.parser import parse_hoja_carga

    try:
        hc = parse_hoja_carga(HOJA_CARGA_PDF)
    except Exception:
        return []
    ce_map = _ce_per_unit_map()
    desc_map = _description_map()
    out: list[DeliveredLine] = []
    for ln in hc.lines:
        if ln.section != "envases":
            continue
        out.append(
            DeliveredLine(
                sku=ln.sku,
                description=desc_map.get(ln.sku, ln.description),
                quantity=ln.quantity,
                unit=ln.unit,
                ce=ce_map.get(ln.sku, 1.0),
                weight_kg=0.0,
                source_ubicacion=ln.ubicacion,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def plan(
    ruta: str,
    fecha: date,
    vehicle_profile: VehicleProfileName = "truck_6p_sidecurtain",
    *,
    familiarity_weight: float = 0.5,
    use_ortools: bool = True,
    prefer_osrm: bool = False,
) -> Plan:
    """Joint route + load + returns optimisation (FR-008).

    Args:
        ruta: route code, e.g. ``"DR0027"``.
        fecha: delivery date.
        vehicle_profile: which YAML profile to fit. Default
            ``truck_6p_sidecurtain`` (the most common in the fleet).
        familiarity_weight: soft penalty pulling the route towards the
            baseline order (0 = ignore baseline; high = match baseline).
            UI exposes this as the "familiar vs optimal" slider.
        use_ortools: ``False`` forces the pure-Python heuristic.
        prefer_osrm: pass-through to the distance matrix; default
            ``False`` because the public OSRM server is slow.

    Returns:
        A :class:`Plan` with ``stops`` and ``slot_assignments``.
    """
    profile = _load_vehicle(vehicle_profile)
    geo = _customers_geo()
    explanations: list[Explanation] = []

    # 1. Build per-stop demand. Prefer parquet; fall back to paperwork
    #    for the demo (DR0027 / 2026-05-08) when that day isn't in the
    #    deliveries dataset.
    stops, _ = _build_stop_demands_from_deliveries(ruta, fecha)
    baseline_order: list[int] = []
    if not stops:
        stops, baseline = _build_stop_demands_from_paperwork(ruta, fecha)
        baseline_order = [s.customer_id for s in baseline]
    else:
        baseline_order = [s.customer_id for s in stops]

    if not stops:
        raise ValueError(
            f"No deliveries found for ruta={ruta!r} date={fecha!r}."
        )

    # 2. Build RouteStop list. Drop stops without geocoding (we can't
    #    place them on a map) but keep them in the demand list so the
    #    load packer sees the right total — we'll insert them at the
    #    end with no ETA.
    route_inputs: list[RouteStop] = []
    geocoded_customer_ids: list[int] = []
    ungeocoded_customer_ids: list[int] = []
    for s in stops:
        info = geo.get(s.customer_id)
        if info and info[2] is not None and info[3] is not None:
            ce = sum(l.ce * l.quantity for l in s.lines)
            route_inputs.append(
                RouteStop(
                    customer_id=s.customer_id,
                    lat=info[2],
                    lon=info[3],
                    ce_demand=ce,
                    time_window=None,
                    service_time_min=10.0,
                )
            )
            geocoded_customer_ids.append(s.customer_id)
        else:
            ungeocoded_customer_ids.append(s.customer_id)

    if not route_inputs:
        raise ValueError(
            f"None of the {len(stops)} stops have lat/lon for ruta={ruta!r}."
        )

    # 3. Solve route.
    rs = solve_route(
        route_inputs,
        DEPOT_LAT_LON,
        capacity_ce=profile.total_capacity_ce,
        baseline_order=baseline_order,
        familiarity_weight=familiarity_weight,
        use_ortools=use_ortools,
        prefer_osrm=prefer_osrm,
    )

    # 4. Re-sequence stops by the optimised order. Append ungeocoded at the end.
    new_seq: list[int] = list(rs.ordered_customer_ids) + ungeocoded_customer_ids
    seq_to_demand: dict[int, StopDemand] = {s.customer_id: s for s in stops}

    resequenced: list[StopDemand] = []
    for i, cid in enumerate(new_seq, start=1):
        if cid not in seq_to_demand:
            continue
        d = seq_to_demand[cid]
        resequenced.append(
            StopDemand(
                sequence=i, customer_id=cid, lines=list(d.lines)
            )
        )

    # 5. Pack load. If returns infeasible later, we'll retry with higher
    #    familiarity weight (which usually mimics the as-is order).
    envase_lines = _envase_lines_from_paperwork()

    # If demand exceeds capacity, scale every stop's line quantities
    # uniformly to fit. This keeps the demo feasible when the recorded
    # CE values run higher than the modelled vehicle capacity (DR-010 +
    # A-31 are still being calibrated).
    total_demand_ce = sum(s.ce_total for s in resequenced) + sum(
        l.ce * l.quantity for l in envase_lines
    )
    if total_demand_ce > profile.total_capacity_ce:
        scale = (profile.total_capacity_ce * 0.95) / total_demand_ce
        scaled: list[StopDemand] = []
        for s in resequenced:
            scaled_lines = [
                DeliveredLine(
                    sku=l.sku,
                    description=l.description,
                    quantity=l.quantity * scale,
                    unit=l.unit,
                    ce=l.ce,
                    weight_kg=l.weight_kg * scale,
                    source_ubicacion=l.source_ubicacion,
                )
                for l in s.lines
            ]
            scaled.append(StopDemand(
                sequence=s.sequence,
                customer_id=s.customer_id,
                lines=scaled_lines,
            ))
        resequenced = scaled
        envase_lines = [
            DeliveredLine(
                sku=l.sku,
                description=l.description,
                quantity=l.quantity * scale,
                unit=l.unit,
                ce=l.ce,
                weight_kg=l.weight_kg * scale,
                source_ubicacion=l.source_ubicacion,
            )
            for l in envase_lines
        ]
        explanations.append(Explanation(
            target="stop", target_id="0",
            reason=(
                f"Carga {total_demand_ce:.0f} CE exceeds {profile.profile_id} "
                f"capacity {profile.total_capacity_ce:.0f} CE; quantities "
                f"scaled by {scale:.2f} for the demo plan."
            ),
        ))

    used_familiarity = familiarity_weight

    def _try_pack_and_returns(stop_list: list[StopDemand]) -> tuple[list[SlotAssignment], list]:
        load_plan = pack_truck(
            profile, stop_list, envase_lines=envase_lines
        )
        # Returns simulation: per-stop returnable CE.
        is_ret = _is_returnable_map()
        per_stop_lines = {s.sequence: s.lines for s in stop_list}
        returnable_ce = estimate_returnable_ce_per_stop(per_stop_lines, is_ret)
        try:
            traces = simulate_returns(load_plan.slot_assignments, returnable_ce)
        except ReturnsInfeasibleError:
            raise
        return load_plan.slot_assignments, traces

    try:
        slot_assignments, returns_trace = _try_pack_and_returns(resequenced)
    except ReturnsInfeasibleError as e:
        # Retry once with a strong familiarity bias — fall back to baseline order.
        used_familiarity = max(familiarity_weight * 10, 50.0)
        rs2 = solve_route(
            route_inputs,
            DEPOT_LAT_LON,
            capacity_ce=profile.total_capacity_ce,
            baseline_order=baseline_order,
            familiarity_weight=used_familiarity,
            use_ortools=use_ortools,
            prefer_osrm=prefer_osrm,
        )
        new_seq2 = list(rs2.ordered_customer_ids) + ungeocoded_customer_ids
        resequenced = []
        for i, cid in enumerate(new_seq2, start=1):
            if cid not in seq_to_demand:
                continue
            d = seq_to_demand[cid]
            resequenced.append(StopDemand(sequence=i, customer_id=cid, lines=list(d.lines)))
        slot_assignments, returns_trace = _try_pack_and_returns(resequenced)
        rs = rs2
        explanations.append(Explanation(
            target="stop", target_id="0",
            reason=f"Returns were infeasible at the optimal route — retried "
                   f"with familiarity_weight={used_familiarity:.1f} (closer to baseline).",
        ))

    # 6. Build StopPlan list.
    eta_by_cid = {cid: eta for cid, eta in zip(rs.ordered_customer_ids, rs.etas)}

    # in_truck_zones_touched per StopPlan: count of distinct truck slots
    # this stop's items live in, which is what the KPI engine consumes
    # (drives service_time = 10 + 2*zones_touched, A-06). The hybrid load
    # packer's whole point is to cluster each customer into one slot, so
    # this is typically 1 — and that's where the operational saving shows
    # up against the baseline's ~5 (avg outbound lines per stop).
    slot_count_by_stop: dict[int, int] = {}
    for slot in slot_assignments:
        if slot.is_envase_zone:
            continue
        for seq in slot.stop_sequences:
            slot_count_by_stop[seq] = slot_count_by_stop.get(seq, 0) + 1

    stop_plans: list[StopPlan] = []
    for stop in resequenced:
        info = geo.get(stop.customer_id, ("?", "", None, None))
        # CE returnable estimate per A-35
        returnable_ce_total = sum(l.ce * l.quantity for l in stop.lines)
        zones_touched = max(1, slot_count_by_stop.get(stop.sequence, 1))
        stop_plans.append(StopPlan(
            sequence=stop.sequence,
            customer_id=stop.customer_id,
            customer_name=info[0],
            address=info[1],
            lat=info[2],
            lon=info[3],
            eta=eta_by_cid.get(stop.customer_id),
            time_window=None,
            payment_condition="CONTADO",
            proforma_total=Decimal(0),
            delivered_lines=list(stop.lines),
            returns_estimated_ce=round(returnable_ce_total * 0.60, 3),
            in_truck_zones_touched=zones_touched,
        ))

    explanations.append(Explanation(
        target="stop", target_id="0",
        reason=(
            f"Route solved with {rs.backend} backend in {rs.total_minutes:.0f} min "
            f"over {rs.total_km:.1f} km. "
            f"familiarity_weight={used_familiarity}."
        ),
    ))

    return Plan(
        ruta=ruta,
        fecha=fecha,
        vehicle_profile=vehicle_profile,
        stops=stop_plans,
        slot_assignments=slot_assignments,
        explanations=explanations,
    )
