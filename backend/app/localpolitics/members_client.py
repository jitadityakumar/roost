"""Thin client for the UK Parliament Members API (issue #61). Fixed public
host, no key; the constituency name only ever feeds a query param (quoted),
never a URL host -- no SSRF concern, same reasoning as app/crime/client.py.

The API can't be queried by GSS code, so the MP is found by the *exact*
constituency name postcodes.io reports (parliamentary_constituency_2024).
Partial names are ambiguous ("Richmond" -> 2 hits), so anything other than
exactly one current exact-name match is treated as "not found"."""
from __future__ import annotations

import json
import urllib.parse
from http.client import HTTPException
from urllib.request import urlopen

BASE = "https://members-api.parliament.uk/api"
REQUEST_TIMEOUT_SECONDS = 15


class MembersApiError(Exception):
    """The request itself failed (network/HTTP/bad JSON) -- distinct from a
    successful request that simply found nothing (find_mp returns None)."""


def _get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    # URLError/HTTPError/TimeoutError/ConnectionResetError are all OSErrors; a
    # truncated body raises HTTPException (IncompleteRead).
    except (OSError, HTTPException, ValueError) as e:
        raise MembersApiError(f"request failed for {url}: {e}") from e


def _general_election_result(constituency_id: int) -> dict:
    """Latest non-notional general election result, or {} if none listed."""
    data = _get(f"/Location/Constituency/{constituency_id}/ElectionResults")
    results = [
        r
        for r in data.get("value") or []
        if r.get("isGeneralElection") and not r.get("isNotional")
    ]
    if not results:
        return {}
    latest = max(results, key=lambda r: r.get("electionDate") or "")
    return {
        "result": latest.get("result"),
        "majority": latest.get("majority"),
        "turnout": latest.get("turnout"),
        "electorate": latest.get("electorate"),
    }


def find_mp(constituency_name: str) -> dict | None:
    """Returns the sitting MP + latest general-election result for a
    constituency, or None if there isn't exactly one current constituency
    with this exact name (or it has no sitting member). Raises
    MembersApiError if a request fails."""
    data = _get("/Location/Constituency/Search", {"searchText": constituency_name})
    matches = [
        item["value"]
        for item in data.get("items") or []
        if item["value"].get("name") == constituency_name and item["value"].get("endDate") is None
    ]
    if len(matches) != 1:
        return None
    constituency = matches[0]
    member = ((constituency.get("currentRepresentation") or {}).get("member") or {}).get("value")
    if not member:
        return None
    party = member.get("latestParty") or {}
    colour = party.get("backgroundColour")
    try:
        election = _general_election_result(constituency["id"])
    except MembersApiError:
        election = {}  # the MP is the point; a missing result line isn't worth failing over
    return {
        "members_api_id": constituency["id"],
        "member_id": member["id"],
        "member_name": member["nameFullTitle"],
        "party_name": party.get("name"),
        "party_abbreviation": party.get("abbreviation"),
        # Parliament supplies no colour for some parties/roles (Speaker):
        # stored as NULL, rendered neutral grey by the frontend.
        "party_colour": f"#{colour}" if colour else None,
        "result": election.get("result"),
        "majority": election.get("majority"),
        "turnout": election.get("turnout"),
        "electorate": election.get("electorate"),
    }
