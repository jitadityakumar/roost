import json


def serialize_listing(row: dict) -> dict:
    out = dict(row)
    for field in ("key_features", "nearest_stations_raw", "edited_fields"):
        if out.get(field):
            try:
                out[field] = json.loads(out[field])
            except (TypeError, json.JSONDecodeError):
                pass
    if out.get("rightmove_status"):
        try:
            out["rightmove_status"] = json.loads(out["rightmove_status"])
        except (TypeError, json.JSONDecodeError):
            pass
    for bool_field in ("chain_free", "cash_only", "garden"):
        if out.get(bool_field) is not None:
            out[bool_field] = bool(out[bool_field])
    return out
