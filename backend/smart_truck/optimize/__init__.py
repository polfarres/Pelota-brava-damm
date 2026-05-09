"""Smart Truck optimisation package (Track A).

Modules:

- :mod:`route` — FR-005 VRP-TW solver (OR-Tools or heuristic fallback).
- :mod:`load`  — FR-006/006a hybrid load packer with vehicle access constraints.
- :mod:`returns` — FR-007/007a free-space tracker for returnable inventory.
- :mod:`pipeline` — FR-008 orchestrator route → load → returns.

Public entry point: :func:`smart_truck.optimize.pipeline.plan`.
"""

from smart_truck.optimize.pipeline import plan  # noqa: F401
