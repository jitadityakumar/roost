"""URL validation, host allowlisting (SSRF guard), and Rightmove property id
extraction — all derivable from the URL path alone, no fetch required."""
import re
from urllib.parse import urlparse

ALLOWED_HOSTS = {"www.rightmove.co.uk", "rightmove.co.uk"}

# Matches both /properties/<id> and /property-for-sale/property-<id>.html
PROPERTY_ID_RE = re.compile(r"/propert(?:ies|y-for-sale/property)[-/](\d+)")


class InvalidListingUrlError(ValueError):
    pass


def extract_property_id(url: str) -> int:
    """Validate the URL is a Rightmove property page and return its numeric
    property id, without making any network request."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise InvalidListingUrlError(f"unsupported URL scheme: {parsed.scheme!r}")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise InvalidListingUrlError(
            f"only rightmove.co.uk property URLs are supported, got host: {parsed.hostname!r}"
        )
    match = PROPERTY_ID_RE.search(parsed.path)
    if not match:
        raise InvalidListingUrlError(f"could not find a property id in URL path: {parsed.path!r}")
    return int(match.group(1))


def canonical_url(property_id: int) -> str:
    """Normalized form every submission resolves to, so re-submitting the
    same listing (with different tracking params, mobile vs. web link, etc.)
    dedupes to one row."""
    return f"https://www.rightmove.co.uk/properties/{property_id}"
