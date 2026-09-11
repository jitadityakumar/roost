from app.floorplan import store
from app.listings import store as listings_store

VALID_URL = "https://www.rightmove.co.uk/properties/123456789"


def test_get_baseline_seeded_singleton_empty(isolated_db):
    baseline = store.get_baseline()
    assert baseline["id"] == 1
    assert baseline["rooms"] == []
    assert baseline["shapes"] == []
    assert baseline["active_scale"] is None


def test_put_baseline_round_trips(isolated_db):
    rooms = [{"id": "r1", "name": "Bedroom 1", "color": "#2e7d6b", "type": "bedroom"}]
    shapes = [{"id": "s1", "roomId": "r1", "points": [{"x": 0, "y": 0}], "pxArea": 100.0, "scalePxPerFt": 10.0, "kind": "rect"}]
    updated = store.put_baseline("data:image/png;base64,xx", 800, 600, 22.5, rooms, shapes)
    assert updated["rooms"] == rooms
    assert updated["shapes"] == shapes
    assert updated["active_scale"] == 22.5
    assert updated["image_w"] == 800

    reread = store.get_baseline()
    assert reread["rooms"] == rooms
    assert reread["shapes"] == shapes


def test_listing_trace_round_trips(isolated_db):
    listings_store.create_stub_listing(42, VALID_URL)
    rooms = [{"id": "r1", "name": "Bathroom 1", "color": "#0f7a8a", "type": "bathroom"}]
    shapes = [{"id": "s1", "roomId": "r1", "points": [{"x": 1, "y": 1}], "pxArea": 50.0, "scalePxPerFt": 5.0, "kind": "poly"}]
    saved = store.put_listing_trace(42, "01.jpeg", 1200, 900, 18.0, rooms, shapes)
    assert saved["listing_id"] == 42
    assert saved["image_path"] == "01.jpeg"
    assert saved["rooms"] == rooms

    fetched = store.get_listing_trace(42, "01.jpeg")
    assert fetched["shapes"] == shapes


def test_listing_trace_missing_returns_none(isolated_db):
    assert store.get_listing_trace(999, "01.jpeg") is None


def test_put_listing_trace_upserts_same_key(isolated_db):
    listings_store.create_stub_listing(1, VALID_URL)
    store.put_listing_trace(1, "01.jpeg", 100, 100, 10.0, [], [])
    updated = store.put_listing_trace(1, "01.jpeg", 100, 100, 11.0, [], [])
    assert updated["active_scale"] == 11.0
    all_traces = store.list_listing_traces(1)
    assert len(all_traces) == 1


def test_list_listing_traces_multiple_images(isolated_db):
    listings_store.create_stub_listing(1, VALID_URL)
    store.put_listing_trace(1, "01.jpeg", 100, 100, 10.0, [], [])
    store.put_listing_trace(1, "02.jpeg", 100, 100, 10.0, [], [])
    traces = store.list_listing_traces(1)
    assert {t["image_path"] for t in traces} == {"01.jpeg", "02.jpeg"}


def test_get_active_trace_picks_most_recently_updated_with_shapes(isolated_db):
    listings_store.create_stub_listing(1, VALID_URL)
    room = [{"id": "r1", "name": "R", "color": "#000", "type": "bedroom"}]
    shape = [{"id": "s1", "roomId": "r1", "points": [], "pxArea": 10.0, "scalePxPerFt": 1.0, "kind": "rect"}]
    store.put_listing_trace(1, "01.jpeg", 100, 100, 10.0, [], [])  # no shapes yet
    store.put_listing_trace(1, "02.jpeg", 100, 100, 10.0, room, shape)
    active = store.get_active_trace(1)
    assert active["image_path"] == "02.jpeg"


def test_get_active_trace_none_when_no_shapes_anywhere(isolated_db):
    listings_store.create_stub_listing(1, VALID_URL)
    store.put_listing_trace(1, "01.jpeg", 100, 100, 10.0, [], [])
    assert store.get_active_trace(1) is None
