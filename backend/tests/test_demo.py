"""Smoke tests for the end-to-end demo runner (``smart_truck.demo``)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RECURSOS = REPO_ROOT / "Hackaton" / "DAMM" / "RECURSOS"


def test_demo_module_importable() -> None:
    """Module imports without raising — guards against typos and broken
    imports across the dependent package surface."""
    from smart_truck import demo  # noqa: F401


@pytest.mark.skipif(
    not (RECURSOS / "Hoja Carga.pdf").exists(),
    reason="Sample PDFs not present.",
)
def test_demo_main_runs_no_pdfs(monkeypatch, capsys) -> None:
    """End-to-end execution in ``--no-pdfs`` mode (fastest path).

    Doesn't reach the network: ``--prefer-osrm`` is OFF by default so
    the KPI engine uses haversine. Track A's optimiser is expected to
    be unavailable, so the script stays in baseline-only mode.
    """
    from smart_truck import demo

    monkeypatch.setattr(
        "sys.argv",
        ["smart_truck.demo", "--no-pdfs"],
    )
    rc = demo.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Reconstructing baseline plan" in out
    assert "Track A optimiser not yet available" in out or "Plan produced" in out
    assert "in_truck_searches" in out
    assert "Done" in out


@pytest.mark.skipif(
    not (RECURSOS / "Hoja Carga.pdf").exists(),
    reason="Sample PDFs not present.",
)
def test_demo_main_emits_pdfs(monkeypatch, tmp_path) -> None:
    """When PDFs are not skipped, both files land in the output dir."""
    from smart_truck import demo

    monkeypatch.setattr(demo, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["smart_truck.demo"])
    rc = demo.main()
    assert rc == 0

    carga = tmp_path / "smart_hoja_carga_DR0027_2026-05-08.pdf"
    ruta = tmp_path / "smart_hoja_ruta_DR0027_2026-05-08.pdf"
    assert carga.exists() and carga.stat().st_size > 1000
    assert ruta.exists() and ruta.stat().st_size > 500
    assert carga.read_bytes()[:5] == b"%PDF-"
    assert ruta.read_bytes()[:5] == b"%PDF-"
