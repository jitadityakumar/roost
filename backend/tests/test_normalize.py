import pytest

from app.listings.normalize import detect_garden, detect_parking, parse_price_gbp


@pytest.mark.parametrize(
    "price_text,expected",
    [
        ("£475,000", 475000),
        ("£1,250,000", 1250000),
        (None, None),
        ("", None),
        ("POA", None),
    ],
)
def test_parse_price_gbp(price_text, expected):
    assert parse_price_gbp(price_text) == expected


def test_detect_garden_from_structured_features():
    assert detect_garden({"garden": ["Private"]}, []) is True


def test_detect_garden_from_key_features_fallback():
    assert detect_garden({"garden": []}, ["Lovely rear garden"]) is True


def test_detect_garden_no_mention_returns_none():
    assert detect_garden({"garden": []}, ["Modern kitchen"]) is None


def test_detect_garden_handles_missing_inputs():
    assert detect_garden(None, None) is None


def test_detect_parking_from_structured_features():
    assert detect_parking({"parking": [{"displayText": "Off street"}]}, []) == "Off street"


@pytest.mark.parametrize(
    "key_features,expected",
    [
        (["Garage included"], "Garage"),
        (["Off-street parking available"], "Off street"),
        (["Allocated parking space"], "Allocated"),
        (["Long driveway"], "Driveway"),
        (["Parking permit required"], "Yes"),
    ],
)
def test_detect_parking_from_key_features_fallback(key_features, expected):
    assert detect_parking({}, key_features) == expected


def test_detect_parking_no_mention_returns_none():
    assert detect_parking({}, ["Modern kitchen"]) is None
