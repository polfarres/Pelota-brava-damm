"""End-to-end demo runner — one command to produce every pitch artefact.

Reads the source DDIDGP paperwork for the demo carga, reconstructs the
baseline (FR-004), runs the KPI engine (FR-009), and emits Smart Hoja
Carga + Smart Hoja Ruta PDFs (FR-010, FR-011) into
``backend/data/demo_output/``.

The optimiser (Track A) is wired in optionally: if
``smart_truck.optimize.pipeline.plan`` is importable and runs, the KPI
deltas show baseline-vs-optimised. Otherwise the script gracefully
degrades to baseline-only metrics and pass-through PDFs (Descarga
left blank in the Smart Hoja Carga). This means the script is useful
*today* — and gets sharper the moment Track A merges.

Run::

    python -m smart_truck.demo
    python -m smart_truck.demo --no-pdfs
    python -m smart_truck.demo --prefer-osrm
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .baseline import RECURSOS_DIR, reconstruct_baseline
from .kpi import compute_kpis, measure
from .models import Plan
from .paperwork.emitter import emit_smart_hoja_carga, emit_smart_hoja_ruta
from .paperwork.parser import parse_hoja_carga, parse_hoja_ruta

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "backend" / "data" / "demo_output"

DEFAULT_RUTA = "DR0027"
DEFAULT_FECHA = "2026-05-08"


def _try_optimise(ruta: str, fecha: date) -> Plan | None:
    """Call Track A's pipeline if it's available; return None otherwise."""
    try:
        from .optimize.pipeline import plan as optimise  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return optimise(ruta, fecha)
    except NotImplementedError:
        return None
    except Exception as e:  # noqa: BLE001 - any optimiser failure → graceful fallback
        print(f"  ! optimiser raised {type(e).__name__}: {e}")
        return None


def main() -> int:
    # On Windows, sys.stdout defaults to cp1252 which can't render the
    # accented characters in the source paperwork (Vehículo, Nº, etc.).
    # The underlying strings are correct UTF-8; this just makes the
    # printed report readable on the team's laptops.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    parser = argparse.ArgumentParser(description="Smart Truck end-to-end demo runner")
    parser.add_argument("--route", default=DEFAULT_RUTA, help="Route code (default DR0027)")
    parser.add_argument("--fecha", default=DEFAULT_FECHA, help="ISO date YYYY-MM-DD (default 2026-05-08)")
    parser.add_argument("--no-pdfs", action="store_true", help="Skip emitting Smart PDFs")
    parser.add_argument(
        "--prefer-osrm",
        action="store_true",
        help="Use OSRM road routing for distance (default: haversine — faster, offline-safe)",
    )
    args = parser.parse_args()

    fecha_d = date.fromisoformat(args.fecha)

    if (args.route, args.fecha) != (DEFAULT_RUTA, DEFAULT_FECHA):
        print(f"NOTE: only {DEFAULT_RUTA} / {DEFAULT_FECHA} has source PDFs in RECURSOS/.")
        print("      The script will use those PDFs anyway — values will be wrong if you")
        print("      meant a different carga.")
        print()

    carga_pdf = RECURSOS_DIR / "Hoja Carga.pdf"
    ruta_pdf = RECURSOS_DIR / "Hoja Ruta.pdf"
    if not carga_pdf.exists() or not ruta_pdf.exists():
        print(f"ERROR: source PDFs not found in {RECURSOS_DIR}", file=sys.stderr)
        return 1

    print("=" * 60)
    print(f"Smart Truck end-to-end demo")
    print(f"  Route: {args.route} | Date: {args.fecha}")
    print(f"  Distance backend: {'OSRM (network)' if args.prefer_osrm else 'haversine (offline)'}")
    print("=" * 60)
    print()

    # 1) Parse source paperwork.
    print("[1/5] Parsing source paperwork...")
    hc = parse_hoja_carga(carga_pdf)
    hr = parse_hoja_ruta(ruta_pdf)
    n_lleno = sum(1 for ln in hc.lines if ln.section in ("lleno", "lleno_sin_ubic"))
    n_envases = sum(1 for ln in hc.lines if ln.section == "envases")
    print(
        f"      Hoja Carga: nº_carga={hc.nº_carga}, vehículo={hc.vehiculo}, "
        f"driver {hc.repartidor_id} {hc.repartidor_name}"
    )
    print(
        f"      Hoja Ruta:  {len(hr.stops)} stops, total {hr.total_carga} €, "
        f"cash {hr.total_cobro} €"
    )
    print(f"      Outbound lines={n_lleno}, envases={n_envases}")
    print()

    # 2) Reconstruct baseline.
    print("[2/5] Reconstructing baseline plan...")
    baseline = reconstruct_baseline(carga_pdf, ruta_pdf)
    n_geocoded = sum(1 for s in baseline.stops if s.lat is not None)
    n_with_tw = sum(1 for s in baseline.stops if s.time_window is not None)
    print(
        f"      vehicle_profile={baseline.vehicle_profile}, "
        f"stops={len(baseline.stops)}, slots={len(baseline.slot_assignments)}"
    )
    print(f"      geocoded={n_geocoded}/{len(baseline.stops)}, with-time-window={n_with_tw}")
    print()

    # 3) Try the optimiser (Track A); fall back gracefully.
    print("[3/5] Running optimised plan (Track A)...")
    plan = _try_optimise(args.route, fecha_d)
    if plan is None:
        print("      Track A optimiser not yet available — running in baseline-only mode.")
    else:
        print(
            f"      Plan produced: stops={len(plan.stops)}, "
            f"slots={len(plan.slot_assignments)}, profile={plan.vehicle_profile}"
        )
    print()

    # 4) KPI engine.
    print("[4/5] Computing KPIs...")
    if plan is not None:
        summary = compute_kpis(baseline, plan, prefer_osrm=args.prefer_osrm)
        print(f"      improvements: {summary.improvement_count}/5")
        for d in summary.deltas:
            ok = "[OK]" if d.is_improvement else "[--]"
            arrow = "DOWN" if d.delta < 0 else ("UP  " if d.delta > 0 else "EQ  ")
            print(
                f"      {ok} {d.metric:30s} "
                f"{d.baseline:10.2f} -> {d.proposed:10.2f}  "
                f"{arrow} {abs(d.delta_pct):.1f}%"
            )
    else:
        m = measure(baseline, prefer_osrm=args.prefer_osrm)
        print("      Baseline metrics (no Plan to compare yet):")
        for k, v in m.items():
            print(f"      - {k:30s} {v:10.2f}")
    print()

    # 5) Emit Smart PDFs.
    if args.no_pdfs:
        print("[5/5] Skipping PDF emission (--no-pdfs).")
    else:
        print("[5/5] Emitting Smart PDFs...")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        carga_out = OUTPUT_DIR / f"smart_hoja_carga_{args.route}_{args.fecha}.pdf"
        ruta_out = OUTPUT_DIR / f"smart_hoja_ruta_{args.route}_{args.fecha}.pdf"
        emit_smart_hoja_carga(hc, plan=plan, output_path=carga_out)
        emit_smart_hoja_ruta(hr, plan=plan, output_path=ruta_out)
        print(f"      {carga_out.relative_to(REPO_ROOT)} ({carga_out.stat().st_size:,} bytes)")
        print(f"      {ruta_out.relative_to(REPO_ROOT)} ({ruta_out.stat().st_size:,} bytes)")
    print()

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
