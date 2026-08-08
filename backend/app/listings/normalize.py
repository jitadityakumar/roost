"""Normalization helpers applied when writing an extracted Rightmove payload
into the listings table: numeric price parsing and the light heuristics used
to read garden/parking off Rightmove's own key_features bullets (still a
'rightmove' source — not the free-text description, no LLM involved)."""
import re
from datetime import datetime


def sqm_to_sqft(sqm: float) -> float:
    return round(sqm * 10.7639, 1)


def parse_yyyymmdd_date(date_text) -> str | None:
    """Rightmove's analyticsInfo.analyticsProperty.added is 'YYYYMMDD' ->
    ISO 'YYYY-MM-DD' for display. None if missing or not a valid date."""
    if not date_text:
        return None
    try:
        return datetime.strptime(str(date_text), "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def parse_price_gbp(price_text) -> int | None:
    """'£475,000' -> 475000. Rightmove never lists sub-pound amounts."""
    if not price_text:
        return None
    digits = re.sub(r"[^\d]", "", str(price_text))
    return int(digits) if digits else None


_PARKING_PATTERNS = [
    (re.compile(r"garage", re.I), "Garage"),
    (re.compile(r"off[\s-]?street parking", re.I), "Off street"),
    (re.compile(r"allocated parking", re.I), "Allocated"),
    (re.compile(r"driveway", re.I), "Driveway"),
    (re.compile(r"parking", re.I), "Yes"),
]


def detect_garden(features: dict | None, key_features: list[str] | None) -> bool | None:
    """Rightmove's structured `features.garden` list first (empty when the
    field simply wasn't filled in, non-empty when it was); key_features
    bullet text as a fallback for listings where the structured field is
    blank but a bullet still mentions it."""
    if features and features.get("garden"):
        return True
    if key_features:
        for feature in key_features:
            if "garden" in feature.lower():
                return True
    return None  # absence of a mention isn't proof there's no garden


def detect_parking(features: dict | None, key_features: list[str] | None) -> str | None:
    if features and features.get("parking"):
        display = features["parking"][0].get("displayText")
        if display:
            return display
    if key_features:
        joined = " | ".join(key_features)
        for pattern, label in _PARKING_PATTERNS:
            if pattern.search(joined):
                return label
    return None
