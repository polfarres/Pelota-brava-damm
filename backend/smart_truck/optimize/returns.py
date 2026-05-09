"""FR-007/007a: free-space tracker for returnables.

After delivering stop *N*, every slot whose ``stop_sequences`` ends at
*N* (or earlier) frees up. Returns at stop *N* are estimated as
``A_35_RETURN_RATE × delivered_returnable_ce`` (per A-35 — flat 60 %
rate). Those returns must fit into the cumulative free space (freed
delivery slots + the envase zone).

If at any point cumulative returns exceed cumulative free space, we
raise :class:`ReturnsInfeasibleError` so the pipeline can re-route or
re-pack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from smart_truck.models import SlotAssignment


RETURN_RATE_FLAT = 0.60  # A-35


class ReturnsInfeasibleError(Exception):
    """Raised when projected returns don't fit into available free space."""


@dataclass
class ReturnsTrace:
    """Per-stop diagnostics produced by :func:`simulate_returns`."""

    stop_sequence: int
    free_ce_after: float
    returns_added_ce: float
    cumulative_returns_ce: float


def simulate_returns(
    slot_assignments: Sequence[SlotAssignment],
    delivered_returnable_ce_by_stop: dict[int, float],
    *,
    return_rate: float = RETURN_RATE_FLAT,
) -> list[ReturnsTrace]:
    """Walk through the route and check returnable inventory fits.

    Args:
        slot_assignments: as produced by :mod:`load`.
        delivered_returnable_ce_by_stop: stop_sequence → CE volume of
            returnable product delivered there. Returns are estimated as
            ``return_rate`` of that volume.
        return_rate: flat fraction of delivered returnable CE that comes
            back as empties (A-35 = 0.60).

    Returns:
        list of :class:`ReturnsTrace`, one per stop in sequence order.

    Raises:
        ReturnsInfeasibleError: if at any stop, cumulative returns
            exceed available freed-up space + envase zone capacity.
    """
    if not delivered_returnable_ce_by_stop:
        return []

    # Total envase zone capacity available from stop 1 (envase slots are
    # empty at start of route per FR-006).
    envase_capacity_ce = sum(
        sa.ce_capacity for sa in slot_assignments if sa.is_envase_zone
    )

    # When does each non-envase slot free up? slot_freed_at[slot_id] is
    # the stop_sequence at which the slot is fully delivered.
    slot_freed_at: dict[str, int] = {}
    slot_capacity: dict[str, float] = {}
    for sa in slot_assignments:
        if sa.is_envase_zone:
            continue
        if not sa.stop_sequences:
            continue
        slot_freed_at[sa.slot_id] = max(sa.stop_sequences)
        slot_capacity[sa.slot_id] = sa.ce_capacity

    sequences = sorted(delivered_returnable_ce_by_stop.keys())
    cumulative_returns = 0.0
    out: list[ReturnsTrace] = []

    for seq in sequences:
        # Free space after delivering at stop `seq`:
        freed_delivery_ce = sum(
            cap for sid, cap in slot_capacity.items()
            if slot_freed_at.get(sid, 1_000_000) <= seq
        )
        free_ce_after = freed_delivery_ce + envase_capacity_ce

        returns_added = delivered_returnable_ce_by_stop[seq] * return_rate
        cumulative_returns += returns_added

        if cumulative_returns - free_ce_after > 1e-6:
            raise ReturnsInfeasibleError(
                f"At stop {seq}: cumulative returns "
                f"{cumulative_returns:.1f} CE > free space {free_ce_after:.1f} CE. "
                f"Re-route or down-size carga."
            )
        out.append(
            ReturnsTrace(
                stop_sequence=seq,
                free_ce_after=free_ce_after,
                returns_added_ce=returns_added,
                cumulative_returns_ce=cumulative_returns,
            )
        )
    return out


def estimate_returnable_ce_per_stop(
    stop_sequences_to_lines: dict[int, Sequence],
    is_returnable_sku: dict[str, bool] | None = None,
) -> dict[int, float]:
    """Helper: compute the returnable CE volume delivered at each stop.

    Args:
        stop_sequences_to_lines: stop_sequence → iterable of
            :class:`smart_truck.models.DeliveredLine`.
        is_returnable_sku: optional override of returnable status per SKU.
            If ``None`` we assume *all* delivered lines are returnable
            (worst-case bound).

    Returns:
        stop_sequence → CE volume of returnable product delivered.
    """
    out: dict[int, float] = {}
    for seq, lines in stop_sequences_to_lines.items():
        ce = 0.0
        for ln in lines:
            ret = True if is_returnable_sku is None else bool(
                is_returnable_sku.get(ln.sku, True)
            )
            if ret:
                ce += ln.ce * ln.quantity
        out[seq] = ce
    return out
