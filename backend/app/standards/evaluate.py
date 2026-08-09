"""Pure evaluation of standards rules against a listing -- no DB access, so
it's trivially testable and safe to call from a hot request path."""
from __future__ import annotations

import operator as op
import re

from app.standards.fields import FIELD_LABELS, field_type

OPERATORS = {
    "lt": op.lt,
    "lte": op.le,
    "gt": op.gt,
    "gte": op.ge,
    "eq": op.eq,
    "neq": op.ne,
}

OPERATOR_SYMBOLS = {
    "lt": "<",
    "lte": "≤",
    "gt": ">",
    "gte": "≥",
    "eq": "=",
    "neq": "≠",
}


def _cast_numeric(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cast_boolean(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("true", "1")


def _cast_epc_band(value) -> str | None:
    """Extracts the leading letter band from either a listing's stored
    "<letter> (<score>)" string or a rule's plain letter value. Bands sort
    correctly as bare characters (A < B < ... < G), so no rank table is
    needed for comparison."""
    if value is None:
        return None
    match = re.match(r"\s*([A-Ga-g])", str(value))
    return match.group(1).upper() if match else None


def _message(field: str, kind: str, listing_value, rule_operator: str, rule_value) -> str:
    label = FIELD_LABELS.get(field, field)
    if kind == "boolean":
        return label if listing_value else f"{label}: false"
    symbol = OPERATOR_SYMBOLS[rule_operator]
    if kind == "epc_band":
        return f"{label} is {listing_value} ({symbol} {rule_value})"
    listing_display = int(listing_value) if listing_value == int(listing_value) else listing_value
    rule_display = int(rule_value) if rule_value == int(rule_value) else rule_value
    return f"{label} is {listing_display} ({symbol} {rule_display})"


def evaluate_listing(listing: dict, rules: list[dict]) -> list[dict]:
    """Returns one entry per enabled rule that matches (i.e. the listing
    violates that standard). A rule whose field is null on the listing, or
    whose field isn't recognised, never matches -- missing data is never
    treated as a violation."""
    violations = []
    for rule in rules:
        if not rule.get("enabled"):
            continue
        field = rule["field"]
        kind = field_type(field)
        if kind is None:
            continue

        listing_value = listing.get(field)
        comparator = OPERATORS.get(rule["operator"])
        if comparator is None:
            continue

        if kind == "numeric":
            lv = _cast_numeric(listing_value)
            rv = _cast_numeric(rule["value"])
        elif kind == "epc_band":
            lv = _cast_epc_band(listing_value)
            rv = _cast_epc_band(rule["value"])
        else:
            lv = _cast_boolean(listing_value)
            rv = _cast_boolean(rule["value"])

        if lv is None or rv is None:
            continue

        if comparator(lv, rv):
            violations.append(
                {
                    "rule_id": rule["id"],
                    "field": field,
                    "field_label": FIELD_LABELS.get(field, field),
                    "operator": rule["operator"],
                    "value": rule["value"],
                    "message": _message(field, kind, lv, rule["operator"], rv),
                }
            )
    return violations
