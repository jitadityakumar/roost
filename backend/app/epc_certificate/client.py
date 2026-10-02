"""Fetches a gov.uk EPC certificate page (issue #115).

Public HTML, no API key. The URL must already have passed
url.canonical_certificate_url -- re-checked here as defence in depth, since
this is the only network call in the package. Redirects are refused: a
certificate page has no reason to redirect, and following one would let the
response come from a host the allowlist never saw.
"""
import urllib.error
import urllib.request

from app.epc_certificate.url import canonical_certificate_url

TIMEOUT_S = 20
MAX_BYTES = 2_000_000
USER_AGENT = "Roost/1.0 (personal house tracker)"


class CertificateFetchError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_certificate_html(url: str) -> str:
    url = canonical_certificate_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=TIMEOUT_S) as resp:
            body = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise CertificateFetchError("certificate not found (404) -- check the URL") from e
        raise CertificateFetchError(f"gov.uk returned HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CertificateFetchError(f"could not reach gov.uk: {e}") from e
    if len(body) > MAX_BYTES:
        raise CertificateFetchError("certificate page unexpectedly large")
    return body.decode("utf-8", errors="replace")
