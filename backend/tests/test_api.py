"""Integration tests for the FastAPI app (FR-012)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smart_truck.api import app

REPO_ROOT = Path(__file__).resolve().parents[2]
RECURSOS = REPO_ROOT / "Hackaton" / "DAMM" / "RECURSOS"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "Smart Truck API"


@pytest.mark.skipif(
    not (RECURSOS / "Hoja Carga.pdf").exists(),
    reason="Sample PDFs not present.",
)
def test_baseline_dr0027_returns_jsonable_plan(client: TestClient) -> None:
    r = client.get("/baseline", params={"ruta": "DR0027", "fecha": "2026-05-08"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ruta"] == "DR0027"
    assert body["fecha"] == "2026-05-08"
    assert body["vehicle_profile"] == "truck_6p_sidecurtain"
    assert len(body["stops"]) == 18
    # Decimal fields serialise as strings.
    proforma_total = body["stops"][0]["proforma_total"]
    assert isinstance(proforma_total, str)


def test_baseline_unknown_route_404(client: TestClient) -> None:
    r = client.get("/baseline", params={"ruta": "DR9999", "fecha": "2026-01-01"})
    assert r.status_code == 404


def test_customer_lookup_known_id(client: TestClient) -> None:
    # 9100627695 is BAR PAVELLO, the first stop on DR0027.
    r = client.get("/customers/9100627695")
    if r.status_code == 404:
        pytest.skip("customers parquet not present")
    assert r.status_code == 200
    body = r.json()
    assert body["customer_id"] == 9100627695
    assert "PAVELLO" in body["name"].upper()


def test_customer_lookup_missing_id_404(client: TestClient) -> None:
    r = client.get("/customers/1")
    assert r.status_code in (404,)


@pytest.mark.skipif(
    not (RECURSOS / "Hoja Carga.pdf").exists(),
    reason="Sample PDFs not present.",
)
def test_get_plan_returns_plan_and_kpi(client: TestClient) -> None:
    r = client.get("/plan/DR0027-2026-05-08")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == "DR0027-2026-05-08"
    plan = body["plan"]
    assert plan["ruta"] == "DR0027"
    assert plan["fecha"] == "2026-05-08"
    assert len(plan["stops"]) > 0
    assert len(plan["slot_assignments"]) > 0
    # A-36: no envase zone in v2.
    assert all(not sa["is_envase_zone"] for sa in plan["slot_assignments"])
    kpi = body["kpi"]
    assert "deltas" in kpi
    assert {d["metric"] for d in kpi["deltas"]} >= {
        "total_km",
        "total_minutes",
        "in_truck_searches",
    }


@pytest.mark.skipif(
    not (RECURSOS / "Hoja Carga.pdf").exists(),
    reason="Sample PDFs not present.",
)
def test_post_plan_returns_plan_and_kpi(client: TestClient) -> None:
    r = client.post("/plan", json={"ruta": "DR0027", "fecha": "2026-05-08"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == "DR0027-2026-05-08"
    assert body["plan"]["ruta"] == "DR0027"
    assert "kpi" in body


def test_get_plan_unknown_run_id_404(client: TestClient) -> None:
    r = client.get("/plan/DR9999-2026-01-01")
    assert r.status_code == 404


def test_get_plan_malformed_run_id_400(client: TestClient) -> None:
    r = client.get("/plan/not-a-run-id")
    assert r.status_code in (400, 404)


def test_smart_carga_pdf_unknown_run_id_404(client: TestClient) -> None:
    r = client.get("/plan/abc/hoja-carga.pdf")
    assert r.status_code == 404


def test_smart_ruta_pdf_unknown_run_id_404(client: TestClient) -> None:
    r = client.get("/plan/abc/hoja-ruta.pdf")
    assert r.status_code == 404


@pytest.mark.skipif(
    not (RECURSOS / "Hoja Carga.pdf").exists(),
    reason="Sample PDFs not present.",
)
def test_smart_carga_pdf_known_run_id_descarga_populated(client: TestClient) -> None:
    """The wired Smart Hoja Carga must have a populated Descarga column
    (slot ids appear in the rendered text), not the pass-through blank."""
    r = client.get("/plan/DR0027-2026-05-08/hoja-carga.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 1000

    import io
    import pdfplumber

    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    # At least one Pn slot id and the per-slot footer must appear.
    import re
    assert "Per slot" in text
    assert re.search(r"\bP\d+\b", text), "no slot ids in rendered Smart Hoja Carga"


@pytest.mark.skipif(
    not (RECURSOS / "Hoja Ruta.pdf").exists(),
    reason="Sample PDFs not present.",
)
def test_smart_ruta_pdf_known_run_id_returns_pdf(client: TestClient) -> None:
    r = client.get("/plan/DR0027-2026-05-08/hoja-ruta.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 500
