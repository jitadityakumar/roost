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
              "active_scale": 22.5, "internal_sqft": 850.0, "rooms": [ROOM], "shapes": [SHAPE]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rooms"] == [ROOM]
    assert body["shapes"] == [SHAPE]
    assert body["internal_sqft"] == 850.0
    assert client.get("/api/admin/floorplan-baseline").json()["rooms"] == [ROOM]


def test_put_baseline_422_on_unknown_room_type(client):
    bad_room = {**ROOM, "type": "garage"}
    resp = client.put(
        "/api/admin/floorplan-baseline",
        json={"active_scale": 10.0, "rooms": [bad_room], "shapes": []},
    )
    assert resp.status_code == 422


def test_put_baseline_silently_drops_legacy_hallway_storage_room(client):
    # hallway_storage was a traceable room type before it became a computed
    # remainder -- a save that still carries one from before this change
    # (e.g. the tracer round-tripping an old baseline unmodified) should
    # succeed by dropping it, not 422 on an opaque "unknown room type".
    legacy_room = {"id": "legacy1", "name": "Hallway/Storage 1", "color": "#000", "type": "hallway_storage"}
    legacy_shape = {**SHAPE, "id": "legacy-shape", "roomId": "legacy1"}
    resp = client.put(
        "/api/admin/floorplan-baseline",
        json={"active_scale": 10.0, "rooms": [ROOM, legacy_room], "shapes": [SHAPE, legacy_shape]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rooms"] == [ROOM]
    assert body["shapes"] == [SHAPE]


def test_put_listing_trace_silently_drops_legacy_hallway_storage_room(client):
    listings_store.create_stub_listing(1, VALID_URL)
    legacy_room = {"id": "legacy1", "name": "Hallway/Storage 1", "color": "#000", "type": "hallway_storage"}
    legacy_shape = {**SHAPE, "id": "legacy-shape", "roomId": "legacy1"}
    resp = client.put(
        "/api/listings/1/floorplan-trace",
        json={"image_path": "01.jpeg", "active_scale": 10.0, "rooms": [ROOM, legacy_room], "shapes": [SHAPE, legacy_shape]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rooms"] == [ROOM]
    assert body["shapes"] == [SHAPE]


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


def test_comparison_uses_baseline_internal_sqft_for_hallway_storage_remainder(client):
    listings_store.create_stub_listing(1, VALID_URL)
    client.patch("/api/listings/1", json={"fields": {"floor_area_sqft": 50}})
    client.put(
        "/api/admin/floorplan-baseline",
        json={"active_scale": 10.0, "internal_sqft": 100.0, "rooms": [ROOM], "shapes": [SHAPE]},
    )
    client.put(
        "/api/listings/1/floorplan-trace",
        json={"image_path": "01.jpeg", "active_scale": 10.0, "rooms": [ROOM], "shapes": [SHAPE]},
    )
    resp = client.get("/api/listings/1/floorplan-comparison")
    assert resp.status_code == 200
    hallway = next(t for t in resp.json()["types"] if t["type"] == "hallway_storage")
    assert hallway["baseline_total"] == 99.0  # 100 internal - 1 traced
    assert hallway["listing_total"] == 49.0  # 50 stated - 1 traced
