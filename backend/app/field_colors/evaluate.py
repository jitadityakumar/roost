"""Pure evaluation of a field's 3-tier (green/amber/red) colour against its
configured threshold rule -- no DB access, mirrors standards/evaluate.py's
null-safety: a missing rule or an unreadable listing value never produces a
colour, just None (frontend renders no chip in that case).

Cutoffs are inclusive on both ends ("at or past the cutoff"), matching the
mockup's EPC framing ("Green at/above C", "Red at/below E") generalized to
the numeric fields too -- documented here since the issue left the exact
boundary semantics as an open item. Red is checked before green so an
admin-misconfigured/overlapping pair resolves to the more conservative
colour rather than being order-dependent on dict iteration."""
from __future__ import annotations

from app.field_colors.fields import EPC_BANDS, field_kind


def _cast_numeric(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cast_epc_band(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    letter = text[0] if text else ""
    return letter if letter in EPC_BANDS else None


def color_for(field: str, value, rule: dict | None) -> str | None:
    if rule is None:
        return None
    kind = field_kind(field)
    if kind is None:
        return None

    if kind == "epc_band":
        lv = _cast_epc_band(value)
        if lv is None:
            return None
        green, red = rule.get("green_cutoff"), rule.get("red_cutoff")
        band_rank = {band: i for i, band in enumerate(EPC_BANDS)}
        if red is not None and band_rank[lv] >= band_rank[red]:
            return "red"
        if green is not None and band_rank[lv] <= band_rank[green]:
            return "green"
        return "amber"

    lv = _cast_numeric(value)
    if lv is None:
        return None
    green = _cast_numeric(rule.get("green_cutoff"))
    red = _cast_numeric(rule.get("red_cutoff"))
    higher_is_better = bool(rule.get("higher_is_better"))

    if red is not None and ((higher_is_better and lv <= red) or (not higher_is_better and lv >= red)):
        return "red"
    if green is not None and ((higher_is_better and lv >= green) or (not higher_is_better and lv <= green)):
        return "green"
    return "amber"


def colors_for_listing(listing: dict, rules: list[dict]) -> dict[str, str]:
    """Returns {field: color} for every configured field that produced a
    colour -- a field with no rule row, or no usable listing value, is
    simply absent (frontend treats a missing key as "no chip"). Also mirrors
    service_charge_pa's colour onto service_charge_pm -- that field has no
    threshold row of its own, per the issue (one set of cutoffs, not two)."""
    by_field = {r["field"]: r for r in rules}
    out = {}
    for field, rule in by_field.items():
        color = color_for(field, listing.get(field), rule)
        if color is not None:
            out[field] = color
    if "service_charge_pa" in out:
        out["service_charge_pm"] = out["service_charge_pa"]
    return out
