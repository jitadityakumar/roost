import pytest

from app.listings import store as listings_store


# --- /api/crime/baselines -------------------------------------------------

def test_list_baselines_empty(client):
    resp = client.get("/api/crime/baselines")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_baseline_fetches_stats_and_persists(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    resp = client.post("/api/crime/baselines", json={"label": "Home", "postcode": "ZZ1 1AA"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["label"] == "Home"
    assert body["postcode"] == "ZZ1 1AA"
    assert client.get("/api/crime/baselines").json() == [body]


def test_create_baseline_422_on_geocode_failure(client, monkeypatch):
    from app.crime.client import CrimeApiError
    from app.routes import crime_baselines as route

    def raise_error(pc):
        raise CrimeApiError("postcode not found")

    monkeypatch.setattr(route.service, "get_or_refresh_stats", raise_error)
    resp = client.post("/api/crime/baselines", json={"label": "Home", "postcode": "NOTREAL"})
    assert resp.status_code == 422
    assert client.get("/api/crime/baselines").json() == []


def test_create_baseline_allows_more_than_four(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    labels = [("A", "ZZ1 1AA"), ("B", "ZZ3 3CC"), ("C", "ZZ4 4DD"), ("D", "ZZ2 2BB"), ("E", "ZZ5 5EE")]
    for label, pc in labels:
        assert client.post("/api/crime/baselines", json={"label": label, "postcode": pc}).status_code == 201
    assert len(client.get("/api/crime/baselines").json()) == 5


def test_delete_baseline(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    created = client.post("/api/crime/baselines", json={"label": "Home", "postcode": "ZZ1 1AA"}).json()
    resp = client.delete(f"/api/crime/baselines/{created['id']}")
    assert resp.status_code == 204
    assert client.get("/api/crime/baselines").json() == []


def test_create_baseline_defaults_is_reference_false(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    created = client.post("/api/crime/baselines", json={"label": "Home", "postcode": "ZZ1 1AA"}).json()
    assert created["is_reference"] == 0


def test_update_baseline(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    created = client.post("/api/crime/baselines", json={"label": "Home", "postcode": "ZZ1 1AA"}).json()
    resp = client.patch(
        f"/api/crime/baselines/{created['id']}", json={"label": "Barnes", "postcode": "SW13 0AA"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] == "Barnes"
    assert body["postcode"] == "SW13 0AA"
    assert client.get("/api/crime/baselines").json() == [body]


def test_update_baseline_preserves_reference_flag(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    created = client.post("/api/crime/baselines", json={"label": "Home", "postcode": "ZZ1 1AA"}).json()
    client.post(f"/api/crime/baselines/{created['id']}/reference")

    resp = client.patch(
        f"/api/crime/baselines/{created['id']}", json={"label": "Barnes", "postcode": "SW13 0AA"}
    )
    assert resp.status_code == 200
    assert resp.json()["is_reference"] == 1


def test_update_baseline_404_for_unknown_id(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    resp = client.patch("/api/crime/baselines/999", json={"label": "Barnes", "postcode": "SW13 0AA"})
    assert resp.status_code == 404


def test_update_baseline_422_on_geocode_failure(client, monkeypatch):
    from app.crime.client import CrimeApiError
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    created = client.post("/api/crime/baselines", json={"label": "Home", "postcode": "ZZ1 1AA"}).json()

    def raise_error(pc):
        raise CrimeApiError("postcode not found")

    monkeypatch.setattr(route.service, "get_or_refresh_stats", raise_error)
    resp = client.patch(f"/api/crime/baselines/{created['id']}", json={"label": "Barnes", "postcode": "NOTREAL"})
    assert resp.status_code == 422
    assert client.get("/api/crime/baselines").json()[0]["label"] == "Home"


def test_set_reference_baseline_clears_previous(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    a = client.post("/api/crime/baselines", json={"label": "A", "postcode": "ZZ1 1AA"}).json()
    b = client.post("/api/crime/baselines", json={"label": "B", "postcode": "ZZ2 2BB"}).json()

    resp = client.post(f"/api/crime/baselines/{a['id']}/reference")
    assert resp.status_code == 200
    assert resp.json()["is_reference"] == 1

    resp = client.post(f"/api/crime/baselines/{b['id']}/reference")
    assert resp.status_code == 200
    assert resp.json()["is_reference"] == 1

    baselines = {row["id"]: row for row in client.get("/api/crime/baselines").json()}
    assert baselines[a["id"]]["is_reference"] == 0
    assert baselines[b["id"]]["is_reference"] == 1


def test_set_reference_baseline_404_for_unknown_id(client):
    resp = client.post("/api/crime/baselines/999/reference")
    assert resp.status_code == 404


def test_set_reference_baseline_bad_id_does_not_clobber_existing_reference(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    a = client.post("/api/crime/baselines", json={"label": "A", "postcode": "ZZ1 1AA"}).json()
    client.post(f"/api/crime/baselines/{a['id']}/reference")

    resp = client.post("/api/crime/baselines/999/reference")
    assert resp.status_code == 404

    baselines = client.get("/api/crime/baselines").json()
    assert baselines[0]["is_reference"] == 1


def test_clear_reference_baseline(client, monkeypatch):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    a = client.post("/api/crime/baselines", json={"label": "A", "postcode": "ZZ1 1AA"}).json()
    client.post(f"/api/crime/baselines/{a['id']}/reference")

    resp = client.delete("/api/crime/baselines/reference")
    assert resp.status_code == 204
    assert client.get("/api/crime/baselines").json()[0]["is_reference"] == 0


# --- /api/listings/{id}/crime ---------------------------------------------

def _make_baseline(client, monkeypatch, label, postcode):
    from app.routes import crime_baselines as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})
    return client.post("/api/crime/baselines", json={"label": label, "postcode": postcode}).json()


def test_get_crime_404_for_unknown_listing(client):
    resp = client.get("/api/listings/999/crime")
    assert resp.status_code == 404


def test_get_crime_unavailable_when_no_postcode(client):
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    resp = client.get("/api/listings/1/crime")
    assert resp.status_code == 200
    body = resp.json()
    assert body["unavailable"] == "listing has no postcode"
    assert body["baselines"] == []


def test_get_crime_compares_against_each_baseline(client, monkeypatch):
    _make_baseline(client, monkeypatch, "Home", "ZZ1 1AA")

    listings_store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    listings_store.apply_extracted_fields(2, {"postcode": "ZZ2 2BB"})

    from app.routes import crime as route

    def fake_get_or_refresh(postcode):
        counts = {"ZZ1 1AA": {"burglary": 2}, "ZZ2 2BB": {"burglary": 6}}
        return {"category_counts": counts[postcode]}

    monkeypatch.setattr(route.service, "get_or_refresh_stats", fake_get_or_refresh)

    resp = client.get("/api/listings/2/crime")
    assert resp.status_code == 200
    body = resp.json()
    assert body["unavailable"] is None
    assert len(body["baselines"]) == 1
    baseline = body["baselines"][0]
    assert baseline["label"] == "Home"
    assert baseline["error"] is None
    assert baseline["is_reference"] is False
    assert baseline["comparison"]["score_ratio"] == pytest.approx(3.0)


def test_get_crime_reports_reference_flag(client, monkeypatch):
    home = _make_baseline(client, monkeypatch, "Home", "ZZ1 1AA")
    client.post(f"/api/crime/baselines/{home['id']}/reference")

    listings_store.create_stub_listing(20, "https://www.rightmove.co.uk/properties/20")
    listings_store.apply_extracted_fields(20, {"postcode": "ZZ2 2BB"})

    from app.routes import crime as route

    monkeypatch.setattr(route.service, "get_or_refresh_stats", lambda pc: {"category_counts": {}})

    resp = client.get("/api/listings/20/crime")
    assert resp.json()["baselines"][0]["is_reference"] is True


def test_get_crime_reports_per_baseline_error_without_failing_request(client, monkeypatch):
    _make_baseline(client, monkeypatch, "Home", "ZZ1 1AA")

    listings_store.create_stub_listing(3, "https://www.rightmove.co.uk/properties/3")
    listings_store.apply_extracted_fields(3, {"postcode": "ZZ2 2BB"})

    from app.crime.client import CrimeApiError
    from app.routes import crime as route

    def fake_get_or_refresh(postcode):
        if postcode == "ZZ2 2BB":
            return {"category_counts": {"burglary": 6}}
        raise CrimeApiError("boom")

    monkeypatch.setattr(route.service, "get_or_refresh_stats", fake_get_or_refresh)

    resp = client.get("/api/listings/3/crime")
    assert resp.status_code == 200
    baseline = resp.json()["baselines"][0]
    assert baseline["comparison"] is None
    assert "boom" in baseline["error"]


def test_get_crime_unavailable_when_listing_geocode_fails(client, monkeypatch):
    _make_baseline(client, monkeypatch, "Home", "ZZ1 1AA")

    listings_store.create_stub_listing(4, "https://www.rightmove.co.uk/properties/4")
    listings_store.apply_extracted_fields(4, {"postcode": "NOTREAL"})

    from app.crime.client import CrimeApiError
    from app.routes import crime as route

    def fake_get_or_refresh(postcode):
        if postcode == "NOTREAL":
            raise CrimeApiError("postcode not found")
        return {"category_counts": {}}

    monkeypatch.setattr(route.service, "get_or_refresh_stats", fake_get_or_refresh)

    resp = client.get("/api/listings/4/crime")
    assert resp.status_code == 200
    body = resp.json()
    assert "postcode not found" in body["unavailable"]
    assert body["baselines"] == []
