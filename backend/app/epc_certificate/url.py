"""Validation of a user-supplied EPC certificate URL (issue #115).

This is the SSRF guard for the certificate fetch: only the gov.uk "Find an
energy certificate" host and its fixed certificate path shape are accepted,
and the stored/fetched URL is rebuilt from the certificate number alone, so
no user-controlled host, path or query string ever reaches urllib.
"""
import re
from urllib.parse import urlparse

HOST = "find-energy-certificate.service.gov.uk"

# Certificate numbers (RRNs) are five dash-separated groups of four digits.
_PATH_RE = re.compile(r"^/energy-certificate/([0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{4})/?$")  # ASCII digits only


class InvalidCertificateUrlError(ValueError):
    pass


def canonical_certificate_url(url: str) -> str:
    """Validate `url` and return its canonical form (https, no query/
    fragment), or raise InvalidCertificateUrlError."""
    try:
        parsed = urlparse((url or "").strip())
        hostname = parsed.hostname
    except ValueError as e:  # e.g. "Invalid IPv6 URL" from a stray "["
        raise InvalidCertificateUrlError(f"malformed URL: {e}") from e
    if parsed.scheme not in ("http", "https"):
        raise InvalidCertificateUrlError(f"unsupported URL scheme: {parsed.scheme!r}")
    if hostname != HOST:
        raise InvalidCertificateUrlError(f"only {HOST} certificate URLs are supported")
    match = _PATH_RE.match(parsed.path)
    if not match:
        raise InvalidCertificateUrlError("not a certificate URL (expected /energy-certificate/<number>)")
    return f"https://{HOST}/energy-certificate/{match.group(1)}"
