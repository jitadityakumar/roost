"""Registry of `listings` fields eligible for admin-configured 3-tier
(green/amber/red) colour coding on the Details section (issue #100). A
strict subset of standards/fields.py's own registry -- reuses its labels
rather than redefining them, except for broadband_top_speed_mbps, which
isn't registered there (it's the new parsed column this issue adds, not a
pre-existing standards field).

chain_free is deliberately absent here: its "green on Yes" highlight is a
hard-coded frontend conditional with no admin rule, per the issue."""
from app.standards.fields import FIELD_LABELS as _STANDARDS_LABELS

NUMERIC_FIELDS = {
    "price_gbp": _STANDARDS_LABELS["price_gbp"],
    "lease_years_remaining": _STANDARDS_LABELS["lease_years_remaining"],
    "service_charge_pa": _STANDARDS_LABELS["service_charge_pa"],
    "floor_area_sqft": _STANDARDS_LABELS["floor_area_sqft"],
    "broadband_top_speed_mbps": "Broadband top speed",
}

# service_charge_pm is deliberately not its own colorable field -- it
# mirrors service_charge_pa's colour by deriving from the annual value
# (evaluate.colors_for_listing), rather than getting a second threshold row.

EPC_BAND_FIELDS = {
    "epc_current": _STANDARDS_LABELS["epc_current"],
}
EPC_BANDS = ("A", "B", "C", "D", "E", "F", "G")

FIELD_LABELS = {**NUMERIC_FIELDS, **EPC_BAND_FIELDS}


def field_kind(field: str) -> str | None:
    if field in NUMERIC_FIELDS:
        return "numeric"
    if field in EPC_BAND_FIELDS:
        return "epc_band"
    return None
