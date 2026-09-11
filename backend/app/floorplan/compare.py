"""Pure comparison maths -- no DB access, so it's unit-testable against
fixed fixtures (mirrors the separation in app/crime/score.py).

Room-type pairing: within each type, both sides are sorted by size
descending and paired rank-for-rank (biggest vs biggest, 2nd vs 2nd, ...).
A rank present on only one side renders as a one-sided row -- the frontend
distinguishes "new" (listing has the extra room) from "n/a" (only the
baseline does) using which of baseline_sqft/listing_sqft is None, the same
convention as Crime.jsx's ratioLabel.
"""

ROOM_TYPES = {
    "bedroom": "Bedroom",
    "reception_kitchen": "Reception / Kitchen",
    "bathroom": "Bathroom",
    "outdoor": "Outdoor Space",
}

OUTDOOR_TYPES = {"outdoor"}

# Hallway/Storage is never traced by hand -- it's the remainder after
# subtracting the traced non-outdoor rooms from a known internal sq ft
# figure (floor_area_sqft for a listing, internal_sqft for the baseline,
# both one-time/already-known inputs rather than something worth drawing).
HALLWAY_STORAGE_TYPE = "hallway_storage"
HALLWAY_STORAGE_LABEL = "Hallway / Storage"


def sqft_of(shape: dict) -> float | None:
    """Sq ft is never stored -- pxArea / scalePxPerFt^2, using the scale
    snapshotted on the shape at draw time (not any "live" scale), so a
    shape with no scale yet contributes no area at all."""
    scale = shape.get("scalePxPerFt")
    if not scale:
        return None
    return shape["pxArea"] / (scale * scale)


def _room_sqft_totals(rooms: list[dict], shapes: list[dict]) -> dict[str, float]:
    totals = {room["id"]: 0.0 for room in rooms}
    for shape in shapes:
        sqft = sqft_of(shape)
        if sqft is None:
            continue
        if shape["roomId"] in totals:
            totals[shape["roomId"]] += sqft
    return totals


def _rooms_by_type(rooms: list[dict], shapes: list[dict]) -> dict[str, list[dict]]:
    totals = _room_sqft_totals(rooms, shapes)
    by_type: dict[str, list[dict]] = {t: [] for t in ROOM_TYPES}
    for room in rooms:
        room_type = room.get("type")
        if room_type not in by_type:
            continue
        by_type[room_type].append({"room": room, "sqft": totals[room["id"]]})
    return by_type


def _delta_pct(candidate: float | None, base: float | None) -> float | None:
    """None means "not comparable" -- either side missing, or the base is
    zero. Caller renders None as "new"/"n/a" depending on which side is
    missing, matching crime/score.py's _ratio convention."""
    if candidate is None or base is None or base == 0:
        return None
    return (candidate - base) / base * 100


def _type_total(by_type: dict[str, list[dict]], room_type: str) -> float:
    return sum(r["sqft"] for r in by_type[room_type])


def compare(
    baseline_rooms: list[dict],
    baseline_shapes: list[dict],
    listing_rooms: list[dict],
    listing_shapes: list[dict],
    listing_floor_area_sqft: float | None = None,
    baseline_internal_sqft: float | None = None,
) -> dict:
    baseline_by_type = _rooms_by_type(baseline_rooms, baseline_shapes)
    listing_by_type = _rooms_by_type(listing_rooms, listing_shapes)

    baseline_traced_indoor = sum(_type_total(baseline_by_type, t) for t in ROOM_TYPES if t not in OUTDOOR_TYPES)
    baseline_outdoor = sum(_type_total(baseline_by_type, t) for t in OUTDOOR_TYPES)
    listing_traced_indoor = sum(_type_total(listing_by_type, t) for t in ROOM_TYPES if t not in OUTDOOR_TYPES)
    listing_outdoor = sum(_type_total(listing_by_type, t) for t in OUTDOOR_TYPES)

    # Hallway/Storage is never traced -- it's whatever's left of the known
    # internal sq ft after subtracting the traced non-outdoor rooms. None
    # (not 0) when the internal sq ft input itself is unknown, so the
    # frontend can render "n/a" rather than implying zero hallway space.
    # Deliberately not clamped to 0: if the traced rooms add up to more than
    # the entered internal sq ft, a negative remainder is a useful signal of
    # a tracing/data-entry mismatch, not something to hide.
    baseline_hallway_storage = None if baseline_internal_sqft is None else baseline_internal_sqft - baseline_traced_indoor
    listing_hallway_storage = None if listing_floor_area_sqft is None else listing_floor_area_sqft - listing_traced_indoor

    baseline_indoor = baseline_internal_sqft if baseline_internal_sqft is not None else baseline_traced_indoor
    listing_indoor = listing_floor_area_sqft if listing_floor_area_sqft is not None else listing_traced_indoor

    summary = {
        "indoor": {
            "baseline": baseline_indoor,
            "listing": listing_indoor,
            "delta_pct": _delta_pct(listing_indoor, baseline_indoor),
        },
        "outdoor": {
            "baseline": baseline_outdoor,
            "listing": listing_outdoor,
            "delta_pct": _delta_pct(listing_outdoor, baseline_outdoor),
        },
        "grand": {
            "baseline": baseline_indoor + baseline_outdoor,
            "listing": listing_indoor + listing_outdoor,
            "delta_pct": _delta_pct(listing_indoor + listing_outdoor, baseline_indoor + baseline_outdoor),
        },
        "floor_area_cross_check": None,
    }
    if listing_floor_area_sqft is not None:
        summary["floor_area_cross_check"] = {
            "traced_indoor": listing_traced_indoor,
            "stated_floor_area": listing_floor_area_sqft,
            "delta_pct": _delta_pct(listing_traced_indoor, listing_floor_area_sqft),
        }

    types = []
    for room_type, label in ROOM_TYPES.items():
        baseline_rooms_of_type = sorted(baseline_by_type[room_type], key=lambda r: r["sqft"], reverse=True)
        listing_rooms_of_type = sorted(listing_by_type[room_type], key=lambda r: r["sqft"], reverse=True)
        if not baseline_rooms_of_type and not listing_rooms_of_type:
            continue

        rows = []
        for i in range(max(len(baseline_rooms_of_type), len(listing_rooms_of_type))):
            baseline_sqft = baseline_rooms_of_type[i]["sqft"] if i < len(baseline_rooms_of_type) else None
            listing_sqft = listing_rooms_of_type[i]["sqft"] if i < len(listing_rooms_of_type) else None
            rows.append(
                {
                    "rank": i + 1,
                    "baseline_sqft": baseline_sqft,
                    "listing_sqft": listing_sqft,
                    "delta_pct": _delta_pct(listing_sqft, baseline_sqft),
                }
            )

        types.append(
            {
                "type": room_type,
                "label": label,
                "baseline_total": _type_total(baseline_by_type, room_type),
                "listing_total": _type_total(listing_by_type, room_type),
                "rooms": rows,
            }
        )

    if baseline_hallway_storage is not None or listing_hallway_storage is not None:
        types.append(
            {
                "type": HALLWAY_STORAGE_TYPE,
                "label": HALLWAY_STORAGE_LABEL,
                "baseline_total": baseline_hallway_storage,
                "listing_total": listing_hallway_storage,
                "rooms": [],
            }
        )

    return {"summary": summary, "types": types}
