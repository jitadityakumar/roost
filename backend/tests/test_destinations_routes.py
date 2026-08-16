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
