"""Hand-crafted albarans for the DR0027 / 2026-05-08 demo carga.

The Hoja Carga PDF gives us aggregate quantities (e.g. 114 ED13 cases)
without per-customer attribution; the per-stop split was done by
proforma proportions and produced fractional units that the picker
can't act on (1.806 ED13 caja per stop, etc.).

For the demo we redefine the carga at smaller, integer-friendly
totals and distribute each SKU across the route's customers using
the largest-remainder method weighted by proforma. The result is a
deterministic per-customer attribution where:

- Every quantity is an integer (no fractional cases or barrels).
- ED13 totals exactly 35 cases — fits the staple column at 35 / 60
  CE in P1 with room to spare.
- Barrels go intact to specific customers (1 ED30 = 4 CE, all to one
  bar, never split).
- Most bars get an ED13 line (the cycle product), matching the
  cross-route analysis that flagged it as the universal staple.

Used by :func:`_build_stop_demands_from_paperwork` when the requested
``(ruta, fecha)`` matches the demo. Real routes from
``deliveries.parquet`` keep their per-customer attribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


# ---------------------------------------------------------------------------
# Demo carga totals — the "invented" Hoja Carga numbers.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _DemoLine:
    sku: str
    qty: int
    unit: str
    ubicacion: str
    ce_per_unit: float
    description: str


DEMO_CARGA_LINES: tuple[_DemoLine, ...] = (
    # Cases (CE = 1 each)
    _DemoLine("ED13",    35, "Caja",   "AA09A1", 1.0, "ESTRELLA DAMM 1/3 RET. PP"),
    _DemoLine("ED15LN",  22, "Caja",   "AA08A1", 1.0, "ESTRELLA DAMM 1/5 LN"),
    _DemoLine("VO13",    18, "Caja",   "AA07A1", 1.0, "VOLL-DAMM 1/3 RET."),
    _DemoLine("VE11",    16, "Caja",   "AA11A1", 1.0, "AGUA VERI 1/1 VIDRIO RET."),
    _DemoLine("VE12SP",   8, "Caja",   "EB03A1", 1.0, "AGUA VERI 1/2 PET CAJA 24U"),
    _DemoLine("0LT0033", 11, "Caja",   "FA06A3", 1.0, "LETONA GRAN CREME PET 1,5L"),
    _DemoLine("0AG0003", 12, "Caja",   "AC08A3", 1.0, "FONT D.OR NATURAL 1L RET 12U"),
    _DemoLine("0RF0014",  9, "Caja",   "BA02A3", 1.0, "COCA COLA 33CL LATA 24U"),
    _DemoLine("EC13",     7, "Caja",   "BA05A1", 1.0, "ESTRELLA DAMM SIN ALCOHOL 1/3"),
    _DemoLine("FD13",     6, "Caja",   "AA06A1", 1.0, "FREE DAMM 1/3 RET."),
    _DemoLine("FDT13",    6, "Caja",   "AA04A1", 1.0, "FREE DAMM TOSTADA 1/3 RET."),
    # Barrels (4 CE) — go intact to specific customers
    _DemoLine("ED30",     4, "Barril", "AA10A1", 4.0, "ESTRELLA DAMM BARRIL 30"),
    _DemoLine("DL30",     2, "Barril", "AC04A1", 4.0, "DAMM LEMON BARRIL 30"),
    # Smaller barrels (2.5 CE)
    _DemoLine("ID20",     2, "Barril", "AC01A1", 2.5, "INEDIT DAMM BARRIL 20L"),
    _DemoLine("DL20",     1, "Barril", "AC03A3", 2.5, "DAMM LEMON BARRIL 20L"),
    _DemoLine("TU20",     2, "Barril", "AC03A2", 2.5, "TURIA BARRIL 20L"),
    # Tubo (CO2 cylinder)
    _DemoLine("TB8",      2, "Tubo",   "AC01A1", 4.0, "BOTELLAS CARBONICO 8 KILOS"),
)


# ---------------------------------------------------------------------------
# Distribution algorithm
# ---------------------------------------------------------------------------


def largest_remainder_distribute(
    total: int,
    weights: list[float],
    min_each: int = 0,
) -> list[int]:
    """Distribute ``total`` integer units across ``len(weights)``
    recipients in proportion to their weights, using the largest-
    remainder method. Sum of the returned list always equals ``total``.

    ``min_each`` guarantees every recipient with weight > 0 gets at
    least that many units (used for the universal-staple SKU like
    ED13 where every bar should receive at least one case).
    """
    n = len(weights)
    if total <= 0 or n == 0:
        return [0] * n

    eligible = [i for i, w in enumerate(weights) if w > 0]
    base_n = len(eligible) if eligible else n
    if min_each * base_n > total:
        # Not enough to give min_each to all eligible — drop min.
        min_each = max(0, total // base_n)

    base = [0] * n
    if min_each > 0:
        targets_for_min = eligible if eligible else list(range(n))
        for i in targets_for_min:
            base[i] = min_each
    remaining = total - sum(base)
    if remaining <= 0:
        return base

    sw = sum(weights)
    if sw <= 0:
        # Even split for the remaining units.
        for k in range(remaining):
            base[k % n] += 1
        return base

    targets = [remaining * w / sw for w in weights]
    floors = [int(t) for t in targets]
    remainders = sorted(
        ((targets[i] - floors[i], i) for i in range(n)),
        reverse=True,
    )
    deficit = remaining - sum(floors)
    for _, i in remainders[:max(0, deficit)]:
        floors[i] += 1
    return [base[i] + floors[i] for i in range(n)]


def _distribute_top_only(total: int, weights: list[float]) -> list[int]:
    """For very small totals (1-3 units), assign one unit each to the
    top customers by weight rather than spreading too thin. A single
    barrel goes to the biggest bar, two barrels go to the top two, etc.
    """
    out = [0] * len(weights)
    if total <= 0 or not weights:
        return out
    order = sorted(range(len(weights)), key=lambda i: -weights[i])
    for k in range(min(total, len(weights))):
        out[order[k]] = 1
    extra = total - sum(out)
    for k in range(extra):
        out[order[k % len(order)]] += 1
    return out


# ---------------------------------------------------------------------------
# Demo trigger + builder
# ---------------------------------------------------------------------------


DEMO_RUTA = "DR0027"
DEMO_FECHA = date(2026, 5, 8)


def is_demo(ruta: str, fecha: date) -> bool:
    return ruta == DEMO_RUTA and fecha == DEMO_FECHA


def build_demo_per_customer_lines(
    customer_weights: list[tuple[int, float]],
) -> dict[int, list[dict[str, Any]]]:
    """Distribute :data:`DEMO_CARGA_LINES` across customers as integers.

    Args:
        customer_weights: ``[(customer_id, proforma_total)]`` in stop
            order. Proforma is used as the distribution weight; rows
            with ``proforma <= 0`` (abono/credit-notes) get weight 0.

    Returns: ``{customer_id: [{sku, description, quantity, unit, ce,
        ubicacion}, ...]}`` with strictly integer quantities.
    """
    weights = [max(0.0, w) for _, w in customer_weights]
    out: dict[int, list[dict[str, Any]]] = {cid: [] for cid, _ in customer_weights}

    # Carga totals where one unit is "rare" (e.g. 1-2 barrels) get the
    # top-customers-only treatment so they're never split into < 1.
    BARREL_LIKE_UNITS = {"Barril", "Tubo"}

    # SKUs that should appear on every customer's albarà (the cycle
    # product). For DR0027 demos this is ED13 — bars order it nearly
    # universally.
    UNIVERSAL_SKUS = {"ED13"}

    for line in DEMO_CARGA_LINES:
        if line.qty <= 0:
            continue
        if line.sku in UNIVERSAL_SKUS:
            attribution = largest_remainder_distribute(
                line.qty, weights, min_each=1,
            )
        elif line.unit in BARREL_LIKE_UNITS or line.qty <= 2:
            attribution = _distribute_top_only(line.qty, weights)
        else:
            attribution = largest_remainder_distribute(line.qty, weights)

        for i, qty in enumerate(attribution):
            if qty == 0:
                continue
            cid = customer_weights[i][0]
            out[cid].append({
                "sku": line.sku,
                "description": line.description,
                "quantity": float(qty),
                "unit": line.unit,
                "ce": line.ce_per_unit,
                "source_ubicacion": line.ubicacion,
            })
    return out
