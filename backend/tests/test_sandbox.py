"""Sandbox behaviour tests: the simulated systems must enforce real rules (validation, duplicates, auth)."""
import pytest
from fastapi.testclient import TestClient

from sandbox import db, seed
from sandbox.app import PORTAL_PASSWORD, PORTAL_USER, app


@pytest.fixture()
def client():
    seed.reset()
    db.set_setting("chaos_level", "0")
    with TestClient(app) as c:
        yield c


def test_inbox_lists_seeded_invoice(client):
    r = client.get("/mail")
    assert r.status_code == 200
    assert "Invoice INV-2041" in r.text


def test_create_bill_validation_and_duplicate(client):
    bad = client.post("/erp/bills", data={"vendor": "Acme Supplies", "invoice_number": "X1",
                                          "amount": "abc", "due_date": "2026-13-01"})
    assert bad.status_code == 422 and "Amount must be a number" in bad.text

    ok = client.post("/erp/bills", data={"vendor": "Acme Supplies", "invoice_number": "INV-2041",
                                         "amount": "4,820.50", "due_date": seed.EXPECTED["acme_latest"]["due_date"]},
                     follow_redirects=False)
    assert ok.status_code == 303
    bills = [b for b in db.dump_state()["bills"] if b["invoice_number"] == "INV-2041"]
    assert len(bills) == 1 and bills[0]["amount"] == 4820.50

    dup = client.post("/erp/bills", data={"vendor": "Acme Supplies", "invoice_number": "INV-2041",
                                          "amount": "1", "due_date": "2026-12-01"})
    assert dup.status_code == 422 and "Duplicate" in dup.text


def test_portal_requires_login(client):
    r = client.get("/portal/invoices", follow_redirects=False)
    assert r.status_code == 302 and "/portal/login" in r.headers["location"]
    bad = client.post("/portal/login", data={"username": PORTAL_USER, "password": "nope"})
    assert bad.status_code == 401
    good = client.post("/portal/login", data={"username": PORTAL_USER, "password": PORTAL_PASSWORD})
    assert good.status_code == 200 and "GX-5531" in good.text


def test_chaos_full_level_injects_faults(client):
    client.post("/admin/chaos", json={"level": 1.0, "seed": 7})
    statuses = {client.get("/helpdesk").status_code for _ in range(12)}
    assert 503 in statuses
    assert client.get("/admin/chaos").json()["log"]
    client.post("/admin/chaos", json={"level": 0})


def test_expected_totals_match_pdfs():
    assert seed.EXPECTED["acme_latest"]["amount"] == 4820.50
    assert seed.EXPECTED["globex_latest"]["amount"] == 7342.18
