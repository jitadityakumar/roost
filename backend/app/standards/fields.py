"""Registry of `listings` columns that can be used in a standards rule, and
the operators each field type accepts. The single source of truth for both
rule validation (store.py) and evaluation (evaluate.py)."""

NUMERIC_FIELDS = {
    "price_gbp": "Price",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "lease_years_remaining": "Lease years remaining",
    "service_charge_pa": "Service charge (per yr)",
    "service_charge_pm": "Service charge (per mo)",
    "floor_area_sqft": "Floor area (sq ft)",
    # Computed, not a raw `listings` column -- injected onto the listing
    # dict at evaluate_listing's call site (routes/listings.py::get_listing)
    # rather than stored in the DB. Value is in minutes, not seconds --
    # there's no unit-conversion layer elsewhere in this module, so this
    # field's stored/compared value and its label must both stay minutes.
    "min_walk_minutes": "Walking time to nearest station (min)",
}

BOOLEAN_FIELDS = {
    "cash_only": "Cash buyers only",
    "chain_free": "Chain free",
    "garden": "Garden",
}

# `epc_current` is stored as "<letter> (<score>)" (e.g. "C (73)") -- rules
# compare on the letter band only. A is best, G is worst, and the bands
# already sort correctly as plain characters (A < B < ... < G), so no
# separate rank table is needed -- lt/gt read naturally as "better than" /
# "worse than".
EPC_BAND_FIELDS = {
    "epc_current": "EPC current",
}
EPC_BANDS = ("A", "B", "C", "D", "E", "F", "G")

FIELD_LABELS = {**NUMERIC_FIELDS, **BOOLEAN_FIELDS, **EPC_BAND_FIELDS}

NUMERIC_OPERATORS = ("lt", "lte", "gt", "gte", "eq", "neq")
BOOLEAN_OPERATORS = ("eq", "neq")
EPC_BAND_OPERATORS = ("lt", "lte", "gt", "gte", "eq", "neq")


def field_type(field: str) -> str | None:
    if field in NUMERIC_FIELDS:
        return "numeric"
    if field in BOOLEAN_FIELDS:
        return "boolean"
    if field in EPC_BAND_FIELDS:
        return "epc_band"
    return None


def is_valid_operator(field: str, operator: str) -> bool:
    kind = field_type(field)
    if kind == "numeric":
        return operator in NUMERIC_OPERATORS
    if kind == "boolean":
        return operator in BOOLEAN_OPERATORS
    if kind == "epc_band":
        return operator in EPC_BAND_OPERATORS
    return False
