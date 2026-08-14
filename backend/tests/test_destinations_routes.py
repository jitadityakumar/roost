def test_create_destination(client):
    resp = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "pad", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["crs"] == "PAD"


def test_create_destination_rejects_invalid_time(client):
    resp = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "8:30"},
    )
    assert resp.status_code == 422


def test_create_destination_rejects_out_of_range_day_of_week(client):
    resp = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 7, "time": "08:30"},
    )
    assert resp.status_code == 422


def test_list_destinations(client):
    client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    )
    resp = client.get("/api/destinations")
    assert len(resp.json()) == 1


def test_patch_destination_toggle_enabled(client):
    d = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    ).json()
    resp = client.patch(f"/api/destinations/{d['id']}", json={"enabled": False})
    assert resp.json()["enabled"] == 0


def test_patch_unknown_destination_404(client):
    resp = client.patch("/api/destinations/999", json={"enabled": False})
    assert resp.status_code == 404


def test_delete_destination(client):
    d = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    ).json()
    resp = client.delete(f"/api/destinations/{d['id']}")
    assert resp.status_code == 204
    assert client.get("/api/destinations").json() == []


def test_station_search(client):
    resp = client.get("/api/destinations/stations/search", params={"q": "padd"})
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert any("Paddington" in n for n in names)


def test_station_search_blank_query_returns_empty(client):
    resp = client.get("/api/destinations/stations/search", params={"q": ""})
    assert resp.json() == []
