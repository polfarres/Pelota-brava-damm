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


def test_post_plan_stub_returns_501(client: TestClient) -> None:
    r = client.post("/plan", json={"ruta": "DR0027", "fecha": "2026-05-08"})
    assert r.status_code == 501


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
def test_smart_carga_pdf_known_run_id_returns_pdf(client: TestClient) -> None:
    r = client.get("/plan/DR0027-2026-05-08/hoja-carga.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 1000


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
