import pytest

from app.listings.url_utils import InvalidListingUrlError, canonical_url, extract_property_id


@pytest.mark.parametrize(
    "url,expected_id",
    [
        ("https://www.rightmove.co.uk/properties/123456789", 123456789),
        ("http://www.rightmove.co.uk/properties/1", 1),
        ("https://rightmove.co.uk/properties/42", 42),
        (
            "https://www.rightmove.co.uk/property-for-sale/property-987654321.html",
            987654321,
        ),
        ("https://www.rightmove.co.uk/properties/123456789?channel=RES_BUY", 123456789),
    ],
)
def test_extract_property_id_valid(url, expected_id):
    assert extract_property_id(url) == expected_id


def test_extract_property_id_rejects_wrong_scheme():
    with pytest.raises(InvalidListingUrlError):
        extract_property_id("ftp://www.rightmove.co.uk/properties/123")


@pytest.mark.parametrize(
    "host",
    [
        "evil.example.com",
        "rightmove.co.uk.evil.com",
        "www.zoopla.co.uk",
        "notrightmove.co.uk",
    ],
)
def test_extract_property_id_rejects_disallowed_host(host):
    with pytest.raises(InvalidListingUrlError):
        extract_property_id(f"https://{host}/properties/123")


def test_extract_property_id_rejects_missing_id():
    with pytest.raises(InvalidListingUrlError):
        extract_property_id("https://www.rightmove.co.uk/property-for-sale/")


def test_canonical_url():
    assert canonical_url(123456789) == "https://www.rightmove.co.uk/properties/123456789"
