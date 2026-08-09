import pytest

from app.listings import store


# --- client ------------------------------------------------------------

def test_fetch_mortgage_calculation_raises_clearly_when_api_base_unset(monkeypatch):
    from app.mortgage import client

    monkeypatch.setattr(client, "MORTGAGE_API_BASE", None)
    with pytest.raises(client.MortgageApiError, match="ROOST_MORTGAGE_API_BASE"):
        client.fetch_mortgage_calculation(425000, 180)


# --- route ---------------------------------------------------------------

@pytest.fixture
def listing_id(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.apply_extracted_fields(1, {"price_gbp": 425000, "service_charge_pm": 180})
    return 1


@pytest.fixture
def listing_id_no_service_charge(client):
    store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    store.apply_extracted_fields(2, {"price_gbp": 650000})
    return 2


def test_get_mortgage_404_for_unknown_listing(client):
    resp = client.get("/api/listings/999/mortgage")
    assert resp.status_code == 404


def test_get_mortgage_returns_result_on_success(client, listing_id, monkeypatch):
    from app.routes import mortgage as mortgage_route

    calls = []

    def fake_fetch(price_gbp, service_charge_pm):
        calls.append((price_gbp, service_charge_pm))
        return {"totalPaid": 900000}

    monkeypatch.setattr(mortgage_route, "fetch_mortgage_calculation", fake_fetch)
    resp = client.get(f"/api/listings/{listing_id}/mortgage")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"result": {"totalPaid": 900000}, "error": None}
    assert calls == [(425000, 180)]


def test_get_mortgage_sends_zero_service_charge_when_null(client, listing_id_no_service_charge, monkeypatch):
    from app.routes import mortgage as mortgage_route

    calls = []

    def fake_fetch(price_gbp, service_charge_pm):
        calls.append((price_gbp, service_charge_pm))
        return {"totalPaid": 900000}

    monkeypatch.setattr(mortgage_route, "fetch_mortgage_calculation", fake_fetch)
    resp = client.get(f"/api/listings/{listing_id_no_service_charge}/mortgage")
    assert resp.status_code == 200
    assert calls == [(650000, None)]


def test_get_mortgage_reports_error_without_failing_request(client, listing_id, monkeypatch):
    from app.mortgage.client import MortgageApiError
    from app.routes import mortgage as mortgage_route

    def raise_error(price_gbp, service_charge_pm):
        raise MortgageApiError("boom")

    monkeypatch.setattr(mortgage_route, "fetch_mortgage_calculation", raise_error)
    resp = client.get(f"/api/listings/{listing_id}/mortgage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] is None
    assert "boom" in body["error"]


def test_get_mortgage_reports_no_price_without_calling_api(client, monkeypatch):
    from app.routes import mortgage as mortgage_route

    store.create_stub_listing(3, "https://www.rightmove.co.uk/properties/3")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not call the mortgage API without a price")

    monkeypatch.setattr(mortgage_route, "fetch_mortgage_calculation", fail_if_called)
    resp = client.get("/api/listings/3/mortgage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] is None
    assert "price" in body["error"]
