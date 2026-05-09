"""FR-007/007a v2: per-pallet free-space tracker for returnables.

Under the v2 load model (A-36) there is **no dedicated envase zone**.
The truck leaves Mollet 100% full of outbound product. Returns absorb
opportunistically into the freed space inside each pallet position as
deliveries happen: when stop *N* is delivered, the cargo bound for that
stop leaves its slot, and the empties from that customer (60% of the
delivered CE per A-35) go back into the same slot's freed space.

Because the return rate is **flat 60% < 100%** (A-35), returns always
fit per pallet — overflow is mathematically impossible. The function
still computes the per-pallet free-space curve and returns it as
diagnostic information for the KPI engine and frontend timeline.

The signature and :class:`ReturnsTrace` dataclass match v1 so existing
consumers (``pipeline.py``, ``api.py``) keep working. The
:class:`ReturnsInfeasibleError` is preserved as a defensive guard but
should never fire under v2's invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from smart_truck.models import SlotAssignment


RETURN_RATE_FLAT = 0.60  # A-35


class ReturnsInfeasibleError(Exception):
    """Defensive guard. Should not fire under v2 (60% < 100% by design)."""


@dataclass
class ReturnsTrace:
    """Per-stop diagnostic produced by :func:`simulate_returns`."""

    stop_sequence: int
    free_ce_after: float           # cumulative free CE after this stop
    returns_added_ce: float        # this stop's empties absorbed
    cumulative_returns_ce: float   # running total of empties stored


def simulate_returns(
    slot_assignments: Sequence[SlotAssignment],
    delivered_returnable_ce_by_stop: dict[int, float],
    *,
    return_rate: float = RETURN_RATE_FLAT,
) -> list[ReturnsTrace]:
    """Walk the route stop-by-stop, simulating per-pallet returns absorption.

    For each stop ``N``:

    1. Slots whose ``stop_sequences`` end at *N* are now fully delivered
       and their full ``ce_capacity`` becomes free. Slots ending earlier
       were already free before *N*.
    2. Returns at stop *N* = ``return_rate × delivered_returnable_ce_by_stop[N]``
       go into one of the freed slots (any of them — empties are
       fungible at the volume level for this trace).
    3. The free-space pool decreases by ``returns_added``.

    Returns a :class:`ReturnsTrace` per stop. Raises
    :class:`ReturnsInfeasibleError` only if cumulative returns exceed
    cumulative freed space — *never expected* under v2 with 60% rate
    and full-truck departure (A-36).
    """
    if not delivered_returnable_ce_by_stop:
        return []

    # Build a per-stop freed-CE map. In v2, a stop's items freeing up
    # at the stop they're delivered — granularity is the stack layer,
    # not the whole slot. We use SlotAssignment.stack[].ce when the
    # packer populated it (v2); otherwise we fall back to the v1
    # whole-slot semantics (slot freed at its max stop_sequence).
    freed_at_stop: dict[int, float] = {}

    for sa in slot_assignments:
        if sa.is_envase_zone:
            # Legacy v1 envase slot: empty from start, freed at sequence 0.
            freed_at_stop[0] = freed_at_stop.get(0, 0.0) + sa.ce_capacity
            continue
        if sa.stack:
            # v2: each layer frees at its own stop sequence.
            for layer in sa.stack:
                freed_at_stop[layer.stop_sequence] = (
                    freed_at_stop.get(layer.stop_sequence, 0.0) + layer.ce
                )
        elif sa.stop_sequences:
            # v1 fallback: whole slot frees at its last stop.
            last = max(sa.stop_sequences)
            freed_at_stop[last] = freed_at_stop.get(last, 0.0) + sa.ce_capacity

    sequences = sorted(delivered_returnable_ce_by_stop.keys())
    cumulative_returns = 0.0
    cumulative_freed = freed_at_stop.get(0, 0.0)  # legacy envase head start
    out: list[ReturnsTrace] = []

    for seq in sequences:
        cumulative_freed += freed_at_stop.get(seq, 0.0)

        returns_added = delivered_returnable_ce_by_stop[seq] * return_rate
        cumulative_returns += returns_added

        free_ce_after = cumulative_freed - cumulative_returns

        if cumulative_returns - cumulative_freed > 1e-6:
            raise ReturnsInfeasibleError(
                f"At stop {seq}: cumulative returns {cumulative_returns:.1f} CE > "
                f"freed pallet capacity {cumulative_freed:.1f} CE. This shouldn't "
                "happen with the v2 model — investigate the load packer."
            )
        out.append(ReturnsTrace(
            stop_sequence=seq,
            free_ce_after=free_ce_after,
            returns_added_ce=returns_added,
            cumulative_returns_ce=cumulative_returns,
        ))
    return out


def estimate_returnable_ce_per_stop(
    stop_sequences_to_lines: dict[int, Sequence],
    is_returnable_sku: dict[str, bool] | None = None,
) -> dict[int, float]:
    """Compute the returnable CE volume delivered at each stop.

    If ``is_returnable_sku`` is omitted, every line is treated as
    returnable (worst-case bound). At the flat 60% return rate (A-35)
    this still always fits in the freed pallet space.
    """
    out: dict[int, float] = {}
    for seq, lines in stop_sequences_to_lines.items():
        ce = 0.0
        for ln in lines:
            returnable = (
                True
                if is_returnable_sku is None
                else bool(is_returnable_sku.get(ln.sku, True))
            )
            if returnable:
                ce += ln.ce * ln.quantity
        out[seq] = ce
    return out
