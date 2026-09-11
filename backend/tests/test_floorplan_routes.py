from app.listings import store as listings_store

VALID_URL = "https://www.rightmove.co.uk/properties/123456789"

ROOM = {"id": "r1", "name": "Bedroom 1", "color": "#2e7d6b", "type": "bedroom"}
SHAPE = {
    "id": "s1",
    "roomId": "r1",
    "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}, {"x": 0, "y": 10}],
    "pxArea": 100.0,
    "scalePxPerFt": 10.0,
    "kind": "rect",
}


# --- baseline --------------------------------------------------------------

def test_get_baseline_seeded_empty(client):
    resp = client.get("/api/admin/floorplan-baseline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rooms"] == []
    assert body["shapes"] == []


def test_put_baseline_round_trips(client):
    resp = client.put(
        "/api/admin/floorplan-baseline",
        json={"image_blob": "data:image/png;base64,xx", "image_w": 800, "image_h": 600,
              "active_scale": 22.5, "rooms": [ROOM], "shapes": [SHAPE]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rooms"] == [ROOM]
    assert body["shapes"] == [SHAPE]
    assert client.get("/api/admin/floorplan-baseline").json()["rooms"] == [ROOM]


def test_put_baseline_422_on_unknown_room_type(client):
    bad_room = {**ROOM, "type": "garage"}
    resp = client.put(
        "/api/admin/floorplan-baseline",
        json={"active_scale": 10.0, "rooms": [bad_room], "shapes": []},
    )
    assert resp.status_code == 422


# --- listing trace -----------------------------------------------------------

def test_get_listing_trace_404_when_none(client):
    listings_store.create_stub_listing(1, VALID_URL)
    resp = client.get("/api/listings/1/floorplan-trace", params={"image_path": "01.jpeg"})
    assert resp.status_code == 404


def test_get_listing_trace_404_when_listing_missing(client):
    resp = client.get("/api/listings/999/floorplan-trace", params={"image_path": "01.jpeg"})
    assert resp.status_code == 404


def test_put_and_get_listing_trace(client):
    listings_store.create_stub_listing(1, VALID_URL)
    put_resp = client.put(
        "/api/listings/1/floorplan-trace",
        json={"image_path": "01.jpeg", "image_w": 1200, "image_h": 900,
              "active_scale": 18.0, "rooms": [ROOM], "shapes": [SHAPE]},
    )
    assert put_resp.status_code == 200
    get_resp = client.get("/api/listings/1/floorplan-trace", params={"image_path": "01.jpeg"})
    assert get_resp.status_code == 200
    assert get_resp.json()["rooms"] == [ROOM]


def test_put_listing_trace_404_when_listing_missing(client):
    resp = client.put(
        "/api/listings/999/floorplan-trace",
        json={"image_path": "01.jpeg", "rooms": [], "shapes": []},
    )
    assert resp.status_code == 404


# --- comparison --------------------------------------------------------------

def test_comparison_404_when_no_listing_trace(client):
    listings_store.create_stub_listing(1, VALID_URL)
    resp = client.get("/api/listings/1/floorplan-comparison")
    assert resp.status_code == 404


def test_comparison_404_when_listing_missing(client):
    resp = client.get("/api/listings/999/floorplan-comparison")
    assert resp.status_code == 404


def test_comparison_happy_path(client):
    listings_store.create_stub_listing(1, VALID_URL)
    client.put("/api/admin/floorplan-baseline", json={"active_scale": 10.0, "rooms": [ROOM], "shapes": [SHAPE]})
    client.put(
        "/api/listings/1/floorplan-trace",
        json={"image_path": "01.jpeg", "active_scale": 10.0, "rooms": [ROOM], "shapes": [SHAPE]},
    )
    resp = client.get("/api/listings/1/floorplan-comparison")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_image_path"] == "01.jpeg"
    assert body["baseline_has_shapes"] is True
    assert body["summary"]["indoor"]["baseline"] == 1.0
    assert body["summary"]["indoor"]["listing"] == 1.0


def test_comparison_includes_floor_area_cross_check(client):
    listings_store.create_stub_listing(1, VALID_URL)
    client.patch("/api/listings/1", json={"fields": {"floor_area_sqft": 500}})
    client.put(
        "/api/listings/1/floorplan-trace",
        json={"image_path": "01.jpeg", "active_scale": 10.0, "rooms": [ROOM], "shapes": [SHAPE]},
    )
    resp = client.get("/api/listings/1/floorplan-comparison")
    assert resp.status_code == 200
    cross_check = resp.json()["summary"]["floor_area_cross_check"]
    assert cross_check["stated_floor_area"] == 500
    assert cross_check["traced_indoor"] == 1.0
