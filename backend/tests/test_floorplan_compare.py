from app.floorplan import compare


def room(id, room_type, name="Room"):
    return {"id": id, "name": name, "color": "#000", "type": room_type}


def shape(room_id, px_area, scale):
    return {"id": f"s-{room_id}-{px_area}", "roomId": room_id, "points": [], "pxArea": px_area, "scalePxPerFt": scale, "kind": "rect"}


def test_sqft_of_uses_per_shape_scale():
    assert compare.sqft_of(shape("r1", 1000, 10)) == 10.0


def test_sqft_of_null_when_no_scale():
    assert compare.sqft_of(shape("r1", 1000, None)) is None
    s = shape("r1", 1000, 0)
    assert compare.sqft_of(s) is None


def test_equal_room_count_pairs_by_rank():
    baseline_rooms = [room("b1", "bedroom"), room("b2", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10), shape("b2", 500, 10)]  # 10, 5 sqft
    listing_rooms = [room("l1", "bedroom"), room("l2", "bedroom")]
    listing_shapes = [shape("l1", 800, 10), shape("l2", 400, 10)]  # 8, 4 sqft

    result = compare.compare(baseline_rooms, baseline_shapes, listing_rooms, listing_shapes)
    bedroom_type = next(t for t in result["types"] if t["type"] == "bedroom")
    assert bedroom_type["rooms"][0]["baseline_sqft"] == 10.0
    assert bedroom_type["rooms"][0]["listing_sqft"] == 8.0
    assert bedroom_type["rooms"][0]["delta_pct"] == -20.0
    assert bedroom_type["rooms"][1]["baseline_sqft"] == 5.0
    assert bedroom_type["rooms"][1]["listing_sqft"] == 4.0


def test_listing_has_more_rooms_than_baseline_renders_new():
    baseline_rooms = [room("b1", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10)]
    listing_rooms = [room("l1", "bedroom"), room("l2", "bedroom")]
    listing_shapes = [shape("l1", 1000, 10), shape("l2", 500, 10)]

    result = compare.compare(baseline_rooms, baseline_shapes, listing_rooms, listing_shapes)
    bedroom_type = next(t for t in result["types"] if t["type"] == "bedroom")
    extra_row = bedroom_type["rooms"][1]
    assert extra_row["baseline_sqft"] is None
    assert extra_row["listing_sqft"] == 5.0
    assert extra_row["delta_pct"] is None


def test_baseline_has_more_rooms_than_listing_renders_missing():
    baseline_rooms = [room("b1", "bedroom"), room("b2", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10), shape("b2", 500, 10)]
    listing_rooms = [room("l1", "bedroom")]
    listing_shapes = [shape("l1", 1000, 10)]

    result = compare.compare(baseline_rooms, baseline_shapes, listing_rooms, listing_shapes)
    bedroom_type = next(t for t in result["types"] if t["type"] == "bedroom")
    missing_row = bedroom_type["rooms"][1]
    assert missing_row["baseline_sqft"] == 5.0
    assert missing_row["listing_sqft"] is None
    assert missing_row["delta_pct"] is None


def test_zero_baseline_rooms_of_a_type_still_shown_as_new():
    baseline_rooms = []
    baseline_shapes = []
    listing_rooms = [room("l1", "bathroom")]
    listing_shapes = [shape("l1", 1000, 10)]

    result = compare.compare(baseline_rooms, baseline_shapes, listing_rooms, listing_shapes)
    bathroom_type = next(t for t in result["types"] if t["type"] == "bathroom")
    assert bathroom_type["rooms"][0]["baseline_sqft"] is None
    assert bathroom_type["rooms"][0]["listing_sqft"] == 10.0


def test_type_absent_on_both_sides_is_omitted():
    baseline_rooms = [room("b1", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10)]
    listing_rooms = [room("l1", "bedroom")]
    listing_shapes = [shape("l1", 1000, 10)]

    result = compare.compare(baseline_rooms, baseline_shapes, listing_rooms, listing_shapes)
    types_present = {t["type"] for t in result["types"]}
    assert types_present == {"bedroom"}


def test_indoor_excludes_outdoor_type():
    baseline_rooms = [room("b1", "bedroom"), room("b2", "outdoor")]
    baseline_shapes = [shape("b1", 1000, 10), shape("b2", 2000, 10)]  # 10, 20
    listing_rooms = [room("l1", "bedroom"), room("l2", "outdoor")]
    listing_shapes = [shape("l1", 1000, 10), shape("l2", 1000, 10)]  # 10, 10

    result = compare.compare(baseline_rooms, baseline_shapes, listing_rooms, listing_shapes)
    assert result["summary"]["indoor"]["baseline"] == 10.0
    assert result["summary"]["outdoor"]["baseline"] == 20.0
    assert result["summary"]["grand"]["baseline"] == 30.0
    assert result["summary"]["indoor"]["listing"] == 10.0
    assert result["summary"]["outdoor"]["listing"] == 10.0


def test_floor_area_cross_check_uses_traced_indoor_vs_stated():
    baseline_rooms = []
    baseline_shapes = []
    listing_rooms = [room("l1", "bedroom")]
    listing_shapes = [shape("l1", 1000, 10)]  # 10 sqft

    result = compare.compare(
        baseline_rooms, baseline_shapes, listing_rooms, listing_shapes, listing_floor_area_sqft=20.0
    )
    cross_check = result["summary"]["floor_area_cross_check"]
    assert cross_check["traced_indoor"] == 10.0
    assert cross_check["stated_floor_area"] == 20.0
    assert cross_check["delta_pct"] == -50.0


def test_floor_area_cross_check_none_when_not_provided():
    result = compare.compare([], [], [], [])
    assert result["summary"]["floor_area_cross_check"] is None


def test_shape_ignored_if_room_id_not_in_rooms():
    # a stale shape pointing at a deleted room shouldn't blow up or get
    # silently attributed to nothing
    baseline_rooms = [room("b1", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10), shape("gone", 500, 10)]
    result = compare.compare(baseline_rooms, baseline_shapes, [], [])
    bedroom_type = next(t for t in result["types"] if t["type"] == "bedroom")
    assert bedroom_type["baseline_total"] == 10.0


# --- hallway/storage remainder (not traced -- derived from internal sq ft) --

def test_hallway_storage_not_traceable():
    # a room with this legacy type contributes nothing -- it's silently
    # ignored, not validated (validation lives at the route layer)
    room_with_stale_type = room("b1", "hallway_storage")
    shape_for_it = shape("b1", 1000, 10)
    result = compare.compare([room_with_stale_type], [shape_for_it], [], [], baseline_internal_sqft=100.0)
    hallway = next(t for t in result["types"] if t["type"] == "hallway_storage")
    assert hallway["baseline_total"] == 100.0  # nothing traceable was subtracted


def test_hallway_storage_omitted_when_no_internal_sqft_known_on_either_side():
    result = compare.compare([], [], [], [])
    assert "hallway_storage" not in {t["type"] for t in result["types"]}


def test_hallway_storage_is_remainder_of_internal_sqft_minus_traced_rooms():
    baseline_rooms = [room("b1", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10)]  # 10 sqft traced
    listing_rooms = [room("l1", "bedroom")]
    listing_shapes = [shape("l1", 500, 10)]  # 5 sqft traced

    result = compare.compare(
        baseline_rooms, baseline_shapes, listing_rooms, listing_shapes,
        listing_floor_area_sqft=50.0, baseline_internal_sqft=100.0,
    )
    hallway = next(t for t in result["types"] if t["type"] == "hallway_storage")
    assert hallway["baseline_total"] == 90.0
    assert hallway["listing_total"] == 45.0
    assert hallway["rooms"] == [
        {"rank": 1, "baseline_sqft": 90.0, "listing_sqft": 45.0, "delta_pct": -50.0}
    ]


def test_hallway_storage_null_on_side_missing_internal_sqft():
    baseline_rooms = [room("b1", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10)]

    result = compare.compare(
        baseline_rooms, baseline_shapes, [], [], baseline_internal_sqft=100.0
    )
    hallway = next(t for t in result["types"] if t["type"] == "hallway_storage")
    assert hallway["baseline_total"] == 90.0
    assert hallway["listing_total"] is None
    assert hallway["rooms"] == [
        {"rank": 1, "baseline_sqft": 90.0, "listing_sqft": None, "delta_pct": None}
    ]


def test_hallway_storage_null_on_baseline_side_missing_internal_sqft():
    listing_rooms = [room("l1", "bedroom")]
    listing_shapes = [shape("l1", 500, 10)]

    result = compare.compare(
        [], [], listing_rooms, listing_shapes, listing_floor_area_sqft=50.0
    )
    hallway = next(t for t in result["types"] if t["type"] == "hallway_storage")
    assert hallway["baseline_total"] is None
    assert hallway["listing_total"] == 45.0
    assert hallway["rooms"] == [
        {"rank": 1, "baseline_sqft": None, "listing_sqft": 45.0, "delta_pct": None}
    ]


def test_hallway_storage_delta_suppressed_when_baseline_remainder_is_negative():
    # base -5 -> candidate -20 is a *worse* mismatch, not an improvement --
    # the plain (candidate - base) / base formula would flip the sign here
    # (a +300% "good" delta), so it must be suppressed to None instead.
    baseline_rooms = [room("b1", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10)]  # 10 traced, more than the 5 internal sqft below
    listing_rooms = [room("l1", "bedroom")]
    listing_shapes = [shape("l1", 2000, 10)]  # 20 traced, more than the 0 internal sqft below

    result = compare.compare(
        baseline_rooms, baseline_shapes, listing_rooms, listing_shapes,
        baseline_internal_sqft=5.0, listing_floor_area_sqft=0.0,
    )
    hallway = next(t for t in result["types"] if t["type"] == "hallway_storage")
    assert hallway["baseline_total"] == -5.0
    assert hallway["listing_total"] == -20.0
    assert hallway["rooms"][0]["delta_pct"] is None


def test_indoor_summary_uses_internal_sqft_when_known_instead_of_traced_sum():
    baseline_rooms = [room("b1", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10)]  # 10 sqft traced

    result = compare.compare(
        baseline_rooms, baseline_shapes, [], [], baseline_internal_sqft=100.0
    )
    assert result["summary"]["indoor"]["baseline"] == 100.0


def test_indoor_summary_falls_back_to_traced_sum_when_internal_sqft_unknown():
    baseline_rooms = [room("b1", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10)]  # 10 sqft traced

    result = compare.compare(baseline_rooms, baseline_shapes, [], [])
    assert result["summary"]["indoor"]["baseline"] == 10.0


def test_hallway_storage_goes_negative_when_traced_rooms_exceed_internal_sqft():
    # deliberately not clamped to 0 -- a negative remainder is a useful
    # signal that the trace and the entered internal sq ft disagree, not
    # something to hide from the user
    baseline_rooms = [room("b1", "bedroom")]
    baseline_shapes = [shape("b1", 1000, 10)]  # 10 sqft traced, more than internal_sqft below

    result = compare.compare(
        baseline_rooms, baseline_shapes, [], [], baseline_internal_sqft=5.0
    )
    hallway = next(t for t in result["types"] if t["type"] == "hallway_storage")
    assert hallway["baseline_total"] == -5.0
