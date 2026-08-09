"""Thin client for mortgage-calculator's /api/v1/calculate endpoint.
Deployers set its address via ROOST_MORTGAGE_API_BASE (no in-repo default --
see app/config.py), same host-config-lives-outside-the-repo precedent as
app/commute/client.py.

No SSRF concern here (unlike Rightmove URL handling in url_utils.py): the
host/port comes from deployer-controlled config, never from user input.
"""
import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.config import MORTGAGE_API_BASE

TIMEOUT_SECONDS = 5


class MortgageApiError(Exception):
    pass


def fetch_mortgage_calculation(price_gbp: int, service_charge_pm: int | None) -> dict:
    if not MORTGAGE_API_BASE:
        raise MortgageApiError(
            "ROOST_MORTGAGE_API_BASE is not set -- the mortgage API's address "
            "must be configured via environment variable, see CLAUDE.md"
        )
    url = f"{MORTGAGE_API_BASE}/api/v1/calculate"
    # serviceCharge defaults to £500/mo if omitted -- must send 0 explicitly
    # when the listing has none (see context.md: keyed on the field being
    # null, not on tenure, since freehold listings can carry estate charges).
    body = json.dumps(
        {
            "propertyValue": price_gbp,
            "serviceCharge": service_charge_pm if service_charge_pm is not None else 0,
        }
    ).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError) as e:
        raise MortgageApiError(f"mortgage API request failed: {e}") from e
