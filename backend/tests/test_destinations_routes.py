_CREATE_BODY = {
    "name": "Office",
    "destination_type": "station",
    "tfl_identifier": "910GPADTON",
    "station_name": "Paddington",
    "day_of_week": 0,
    "time": "08:30",
}


def test_create_destination(client):
    resp = client.post("/api/destinations", json=_CREATE_BODY)
    assert resp.status_code == 201
    body = resp.json()
    assert body["destination_type"] == "station"
    assert body["tfl_identifier"] == "910GPADTON"


def test_create_postcode_destination(client):
    resp = client.post(
        "/api/destinations",
        json={**_CREATE_BODY, "destination_type": "postcode", "tfl_identifier": "NW1 7JN", "station_name": "NW1 7JN"},
    )
    assert resp.status_code == 201
    assert resp.json()["destination_type"] == "postcode"


def test_create_destination_rejects_invalid_destination_type(client):
    resp = client.post("/api/destinations", json={**_CREATE_BODY, "destination_type": "bogus"})
    assert resp.status_code == 422


def test_create_destination_rejects_invalid_time(client):
    resp = client.post("/api/destinations", json={**_CREATE_BODY, "time": "8:30"})
    assert resp.status_code == 422


def test_create_destination_rejects_out_of_range_day_of_week(client):
    resp = client.post("/api/destinations", json={**_CREATE_BODY, "day_of_week": 7})
    assert resp.status_code == 422


def test_list_destinations(client):
    client.post("/api/destinations", json=_CREATE_BODY)
    resp = client.get("/api/destinations")
    assert len(resp.json()) == 1


def test_patch_destination_toggle_enabled(client):
    d = client.post("/api/destinations", json=_CREATE_BODY).json()
    resp = client.patch(f"/api/destinations/{d['id']}", json={"enabled": False})
    assert resp.json()["enabled"] == 0


def test_patch_unknown_destination_404(client):
    resp = client.patch("/api/destinations/999", json={"enabled": False})
    assert resp.status_code == 404


def test_delete_destination(client):
    d = client.post("/api/destinations", json=_CREATE_BODY).json()
    resp = client.delete(f"/api/destinations/{d['id']}")
    assert resp.status_code == 204
    assert client.get("/api/destinations").json() == []


def _fake_journey(duration_minutes):
    return {
        "duration_minutes": duration_minutes,
        "kind": "direct",
        "num_changes": 0,
        "operator": "South Western Railway",
        "origin_crs": "910GWOKING",
        "origin_name": "Woking Rail Station",
        "arrival_name": "Paddington",
        "interchange_crs": None,
        "departure_time": "2026-08-17T08:40:00",
        "arrival_time": "2026-08-17T09:04:00",
    }


def test_patch_destination_recomputes_home_journey(client, monkeypatch):
    # Verifies the PR #49 review finding: editing day_of_week/time/
    # tfl_identifier via PATCH *does* correctly recompute home_journeys
    # (compute_for_destination, triggered by any non-empty PATCH, always
    # calls compute_home_journey with the freshly-updated destination row) --
    # the admin UI just never exposes editing those fields today, so this
    # path is otherwise untested.
    from app import config
    from app.destinations import backfill_queue, compute, journey_store

    monkeypatch.setattr(config, "HOME_LAT", 51.465)
    monkeypatch.setattr(config, "HOME_LON", -0.2407)

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _fake_journey(20))
    d = client.post("/api/destinations", json=_CREATE_BODY).json()
    backfill_queue.wait_until_idle(timeout=5)
    assert journey_store.get_home_journeys()[d["id"]]["duration_minutes"] == 20

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _fake_journey(35))
    client.patch(f"/api/destinations/{d['id']}", json={"time": "09:00"})
    backfill_queue.wait_until_idle(timeout=5)

    assert journey_store.get_home_journeys()[d["id"]]["duration_minutes"] == 35


def test_home_refresh_recomputes(client, monkeypatch):
    # Issue #51's backfill script needs a way to recompute just the home
    # journey (for a sample/test run) without triggering compute_for_destination's
    # full per-listing loop -- this route is synchronous and calls
    # compute_home_journey directly.
    from app import config
    from app.destinations import backfill_queue, compute, journey_store

    monkeypatch.setattr(config, "HOME_LAT", 51.465)
    monkeypatch.setattr(config, "HOME_LON", -0.2407)
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _fake_journey(20))
    d = client.post("/api/destinations", json=_CREATE_BODY).json()
    backfill_queue.wait_until_idle(timeout=5)

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _fake_journey(41))
    resp = client.post(f"/api/destinations/{d['id']}/home-refresh")
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True
    assert resp.json()["duration_minutes"] == 41
    assert journey_store.get_home_journeys()[d["id"]]["duration_minutes"] == 41


def test_home_refresh_unknown_destination_404(client):
    resp = client.post("/api/destinations/999/home-refresh")
    assert resp.status_code == 404


def test_home_refresh_no_home_configured_returns_unresolved(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "HOME_LAT", None)
    monkeypatch.setattr(config, "HOME_LON", None)
    d = client.post("/api/destinations", json=_CREATE_BODY).json()
    resp = client.post(f"/api/destinations/{d['id']}/home-refresh")
    assert resp.status_code == 200
    assert resp.json() == {"resolved": False}


def test_station_search(client, monkeypatch):
    from app.routes import destinations as destinations_routes

    monkeypatch.setattr(
        destinations_routes,
        "search_stop_points",
        lambda q: [{"id": "910GPADTON", "name": "London Paddington", "modes": ["national-rail", "elizabeth-line"]}],
    )
    resp = client.get("/api/destinations/stations/search", params={"q": "padd"})
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert any("Paddington" in n for n in names)


def test_station_search_blank_query_returns_empty(client):
    # search_stop_points itself returns [] for a blank query, no TfL call --
    # exercised for real here (not mocked) since it never reaches the network.
    resp = client.get("/api/destinations/stations/search", params={"q": ""})
    assert resp.json() == []
