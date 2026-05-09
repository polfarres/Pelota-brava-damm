"""FastAPI app — Smart Truck (FR-012).

Endpoints:

- ``GET  /health``                       — liveness.
- ``GET  /baseline?ruta=&fecha=``        — as-is reconstruction
                                           from the source paperwork.
- ``GET  /customers/{id}``               — single customer detail.
- ``POST /plan``                         — run the joint route + load
                                           optimiser. Stub today; wired
                                           when Track A's pipeline lands.
- ``GET  /plan/{run_id}/hoja-carga.pdf`` — Smart Hoja Carga (Track B).
- ``GET  /plan/{run_id}/hoja-ruta.pdf``  — Smart Hoja Ruta (Track B).

Run::

    uvicorn smart_truck.api:app --reload
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .baseline import RECURSOS_DIR, BaselineInputs, reconstruct_baseline
from .kpi import compute_kpis
from .optimize import pipeline
from .paperwork.emitter import emit_smart_hoja_carga, emit_smart_hoja_ruta
from .paperwork.parser import parse_hoja_carga, parse_hoja_ruta

# Map a run_id to the source PDFs we'll emit a Smart variant of.
# Today: only one demo carga is wired. Future: the Plan store yields
# the source PDFs and a Plan together.
_KNOWN_CARGAS: dict[str, tuple[Path, Path]] = {
    "DR0027-2026-05-08": (
        RECURSOS_DIR / "Hoja Carga.pdf",
        RECURSOS_DIR / "Hoja Ruta.pdf",
    ),
}

# Process-lifetime cache: run_id → (Plan, KpiSummary). Populated lazily
# on first GET or recomputed on POST. Keyed by ``{ruta}-{fecha}``.
_PLAN_CACHE: dict[str, tuple[Any, Any]] = {}


def _parse_run_id(run_id: str) -> tuple[str, str]:
    """Split ``DR0027-2026-05-08`` into ``("DR0027", "2026-05-08")``.

    The fecha is always the last 10 characters (``YYYY-MM-DD``); ruta is
    everything before the trailing ``-{fecha}``. This lets us support
    rutas like ``DR0027`` (which contain no hyphen) cleanly.
    """
    if len(run_id) < 12 or run_id[-11] != "-":
        raise HTTPException(
            status_code=400,
            detail=f"run_id must be ``{{ruta}}-YYYY-MM-DD``, got {run_id!r}",
        )
    ruta = run_id[:-11]
    fecha = run_id[-10:]
    return ruta, fecha


def _get_or_compute_plan(ruta: str, fecha_iso: str, *, force: bool = False):
    """Return the cached Plan + KpiSummary, computing on first miss."""
    key = f"{ruta}-{fecha_iso}"
    if force or key not in _PLAN_CACHE:
        if key not in _KNOWN_CARGAS:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"unknown run_id {key!r}. Today only "
                    f"{', '.join(sorted(_KNOWN_CARGAS))} is wired."
                ),
            )
        plan_obj = pipeline.plan(
            ruta, date.fromisoformat(fecha_iso), prefer_osrm=True
        )
        carga_pdf, ruta_pdf = _KNOWN_CARGAS[key]
        baseline = reconstruct_baseline(carga_pdf, ruta_pdf)
        kpis = compute_kpis(baseline, plan_obj, prefer_osrm=True)
        _PLAN_CACHE[key] = (plan_obj, kpis)
    return _PLAN_CACHE[key]

app = FastAPI(title="Smart Truck", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------


def _jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses, dates, Decimals, etc. to JSON-safe
    primitives. Used because we hand FastAPI plain dataclasses rather
    than pydantic models — keeps the contract one-sided."""
    if is_dataclass(obj):
        return _jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Smart Truck API", "version": "0.1.0"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/baseline")
def get_baseline(ruta: str, fecha: str) -> dict[str, Any]:
    """As-is reconstruction (FR-004) for a given ``(ruta, fecha)``.

    Today only ``DR0027 / 2026-05-08`` is wired — that's the only carga
    we have source PDFs for. Future versions will discover PDFs by ruta
    and fecha automatically.
    """
    if (ruta, fecha) != ("DR0027", "2026-05-08"):
        raise HTTPException(
            status_code=404,
            detail=(
                "Only DR0027 / 2026-05-08 has source PDFs for now. "
                "Add a Hoja Carga + Hoja Ruta PDF pair under "
                "Hackaton/DAMM/RECURSOS/ to extend coverage."
            ),
        )
    bp = reconstruct_baseline(
        RECURSOS_DIR / "Hoja Carga.pdf",
        RECURSOS_DIR / "Hoja Ruta.pdf",
    )
    return _jsonable(bp)


@app.get("/customers/{customer_id}")
def get_customer(customer_id: int) -> dict[str, Any]:
    """Single customer record + lat/lon if geocoded."""
    df = BaselineInputs.load().customers
    matches = df[df["customer_id"] == customer_id]
    if matches.empty:
        raise HTTPException(status_code=404, detail=f"customer {customer_id} not found")
    row = matches.iloc[0]
    return {
        "customer_id": int(row["customer_id"]),
        "name": str(row["name"]),
        "street": str(row["street"]),
        "postcode": str(row["postcode"]),
        "city": str(row["city"]),
        "lat": float(row["lat"]) if pd.notna(row.get("lat")) else None,
        "lon": float(row["lon"]) if pd.notna(row.get("lon")) else None,
    }


class PlanRequest(BaseModel):
    ruta: str
    fecha: str  # ISO YYYY-MM-DD
    force: bool = False


@app.post("/plan")
def post_plan(req: PlanRequest) -> dict[str, Any]:
    """Run the joint optimiser and return a Plan + KPI summary.

    Body: ``{ruta, fecha, force?: bool}``. ``force=True`` recomputes;
    otherwise the cached Plan (if any) is returned.
    """
    plan_obj, kpis = _get_or_compute_plan(req.ruta, req.fecha, force=req.force)
    return {
        "run_id": f"{req.ruta}-{req.fecha}",
        "plan": _jsonable(plan_obj),
        "kpi": _jsonable(kpis),
    }


@app.get("/plan/{run_id}")
def get_plan(run_id: str) -> dict[str, Any]:
    """Fetch a previously-computed :class:`Plan` (+ KPI summary) as JSON.

    Response shape: ``{run_id, plan, kpi}`` where ``plan`` mirrors
    :class:`smart_truck.models.Plan` and ``kpi`` mirrors
    :class:`smart_truck.kpi.KpiSummary`.

    The Plan is computed lazily on first request and cached for the
    process lifetime. Today only ``DR0027-2026-05-08`` is wired (the
    only carga we have source PDFs for).
    """
    ruta, fecha = _parse_run_id(run_id)
    plan_obj, kpis = _get_or_compute_plan(ruta, fecha)
    return {
        "run_id": run_id,
        "plan": _jsonable(plan_obj),
        "kpi": _jsonable(kpis),
    }


def _emit_via_tempfile(emitter, source, plan) -> bytes:
    """Run a paperwork emitter into a temp file and return its bytes."""
    with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        out_path = Path(tmp.name)
    try:
        emitter(source, plan=plan, output_path=out_path)
        return out_path.read_bytes()
    finally:
        out_path.unlink(missing_ok=True)


_ROUTE_GEOM_CACHE: dict[str, list[tuple[float, float]]] = {}


@app.get("/plan/{run_id}/route-geometry")
def get_route_geometry(run_id: str) -> dict[str, Any]:
    """Road-following polyline for the optimised route (depot → stops → depot).

    Uses OSRM ``/route`` to fetch the actual driving geometry so the map
    polyline traces real roads instead of straight lines. Cached for the
    process lifetime. Falls back to straight-line ``[lat, lon]`` segments
    if OSRM is unreachable.
    """
    if run_id in _ROUTE_GEOM_CACHE:
        return {"coords": _ROUTE_GEOM_CACHE[run_id]}

    ruta, fecha = _parse_run_id(run_id)
    plan_obj, _ = _get_or_compute_plan(ruta, fecha)

    from .kpi import MOLLET_DEPOT

    waypoints: list[tuple[float, float]] = [MOLLET_DEPOT]
    for s in plan_obj.stops:
        if s.lat is not None and s.lon is not None:
            waypoints.append((s.lat, s.lon))
    waypoints.append(MOLLET_DEPOT)

    coords = _fetch_osrm_route_geometry(waypoints)
    _ROUTE_GEOM_CACHE[run_id] = coords
    return {"coords": coords}


def _fetch_osrm_route_geometry(
    waypoints: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Call OSRM ``/route`` and return ``[(lat, lon), …]``. Falls back to
    the input waypoints (straight-line) on any failure."""
    if len(waypoints) < 2:
        return waypoints
    try:
        import requests

        coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
        url = f"https://router.project-osrm.org/route/v1/driving/{coord_str}"
        r = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("code") != "Ok" or not body.get("routes"):
            raise RuntimeError(f"OSRM /route code={body.get('code')!r}")
        # GeoJSON coords are [lon, lat]; flip to (lat, lon).
        geom = body["routes"][0]["geometry"]["coordinates"]
        return [(lat, lon) for lon, lat in geom]
    except Exception as e:  # noqa: BLE001
        print(f"  OSRM /route unavailable ({type(e).__name__}: {e}); straight-line")
        return waypoints


@app.get("/plan/{run_id}/hoja-carga.pdf")
def get_smart_hoja_carga(run_id: str) -> Response:
    """Smart Hoja Carga PDF (FR-010).

    Resolves the run_id to its source PDF + cached Plan, then emits a
    Smart Hoja Carga whose ``Descarga`` column is populated from the
    optimiser. ``run_id`` format: ``{ruta}-{fecha}``, e.g.
    ``DR0027-2026-05-08``.
    """
    if run_id not in _KNOWN_CARGAS:
        raise HTTPException(
            status_code=404,
            detail=(
                f"unknown run_id {run_id!r}. Today only "
                f"{', '.join(sorted(_KNOWN_CARGAS))} is wired."
            ),
        )
    ruta, fecha = _parse_run_id(run_id)
    plan_obj, _ = _get_or_compute_plan(ruta, fecha)
    carga_pdf, _ = _KNOWN_CARGAS[run_id]
    source = parse_hoja_carga(carga_pdf)
    pdf = _emit_via_tempfile(emit_smart_hoja_carga, source, plan=plan_obj)
    return Response(content=pdf, media_type="application/pdf")


@app.get("/plan/{run_id}/hoja-ruta.pdf")
def get_smart_hoja_ruta(run_id: str) -> Response:
    """Smart Hoja Ruta PDF (FR-011). Reorders rows to the optimised
    sequence and annotates ETAs from the cached Plan."""
    if run_id not in _KNOWN_CARGAS:
        raise HTTPException(
            status_code=404,
            detail=(
                f"unknown run_id {run_id!r}. Today only "
                f"{', '.join(sorted(_KNOWN_CARGAS))} is wired."
            ),
        )
    ruta, fecha = _parse_run_id(run_id)
    plan_obj, _ = _get_or_compute_plan(ruta, fecha)
    _, ruta_pdf = _KNOWN_CARGAS[run_id]
    source = parse_hoja_ruta(ruta_pdf)
    pdf = _emit_via_tempfile(emit_smart_hoja_ruta, source, plan=plan_obj)
    return Response(content=pdf, media_type="application/pdf")
