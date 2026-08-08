#!/usr/bin/env python3
"""Extract structured listing data from a Rightmove property page, and
download its photos/floorplans/EPC graphic alongside it by default.

Rightmove server-renders a full data model into `window.__PAGE_MODEL` as a
flat, self-referential array (each dict/list value is an integer index into
the same array, for deduplication). We fetch the page, pull that blob out,
and resolve it into an ordinary nested JSON structure.
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

PAGE_MODEL_RE = re.compile(r"window\.__PAGE_MODEL\s*=\s*(\{.*?\});?\s*\n")


def fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8")


def resolve_page_model(html: str) -> dict:
    match = PAGE_MODEL_RE.search(html)
    if not match:
        raise ValueError("Could not find window.__PAGE_MODEL in page HTML")
    outer = json.loads(match.group(1))
    arr = json.loads(outer["data"])
    sys.setrecursionlimit(10000)

    def resolve(ref, seen=frozenset()):
        if not isinstance(ref, int):
            return ref
        if ref in seen:
            return None
        val = arr[ref]
        if isinstance(val, dict):
            return {k: resolve(v, seen | {ref}) for k, v in val.items()}
        if isinstance(val, list):
            return [resolve(v, seen | {ref}) for v in val]
        return val

    return resolve(0)


def extract_listing(prop: dict, listing_added_on: str | None = None) -> dict:
    return {
        "id": prop.get("id"),
        "url": f"https://www.rightmove.co.uk/properties/{prop.get('id')}",
        "status": prop.get("status"),
        "price": prop.get("prices", {}).get("primaryPrice"),
        "address": prop.get("address", {}).get("displayAddress"),
        "postcode_outcode": prop.get("address", {}).get("outcode"),
        "postcode_incode": prop.get("address", {}).get("incode"),
        "property_type": prop.get("propertySubType"),
        "bedrooms": prop.get("bedrooms"),
        "bathrooms": prop.get("bathrooms"),
        "tenure": (prop.get("tenure") or {}).get("tenureType"),
        "lease_years_remaining": (prop.get("tenure") or {}).get("yearsRemainingOnLease"),
        "key_features": prop.get("keyFeatures"),
        "listing_added_on": listing_added_on,
        "description": prop.get("text", {}).get("description"),
        "listing_update": (prop.get("listingHistory") or {}).get("listingUpdateReason"),
        "nearest_stations": prop.get("nearestStations"),
        "features": prop.get("features"),
        "num_images": len(prop.get("images") or []),
        "floorplans": prop.get("floorplans"),
        "num_floorplans": len(prop.get("floorplans") or []),
        "epc_graphs": prop.get("epcGraphs"),
        "num_epc_graphs": len(prop.get("epcGraphs") or []),
        "agent_branch": (prop.get("customer") or {}).get("branchDisplayName"),
        "agent_address": (prop.get("customer") or {}).get("displayAddress"),
        "living_costs": prop.get("livingCosts"),
        "broadband": None,
    }


def fetch_broadband_summary(postcode: str) -> dict:
    """Fetch Rightmove's broadband deals summary for a postcode (no space,
    e.g. 'GU227PB'). Returns the raw API JSON."""
    url = f"https://www.rightmove.co.uk/properties/api/broadband/summary/{postcode}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def summarize_broadband(data: dict) -> dict:
    """Reduce the (very large) broadband API response down to the headline
    numbers: fastest available speed/provider and cheapest deal."""
    fastest = data.get("fastestAverageSpeed") or {}
    cheapest = data.get("cheapestDeal") or {}
    return {
        "top_speed": fastest.get("display"),
        "top_speed_category": fastest.get("speedCategory"),
        "top_speed_provider": (fastest.get("provider") or {}).get("name"),
        "num_available_deals": data.get("numberOfAvailableDeals"),
        "cheapest_deal_speed": (cheapest.get("speed") or [{}])[0].get("display"),
        "cheapest_deal_provider": (cheapest.get("provider") or {}).get("name"),
        "cheapest_deal_monthly_cost": (cheapest.get("subscription") or {}).get("averageMonthlyCost"),
    }


def download_file(url: str, dest_path: str):
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp, open(dest_path, "wb") as f:
        f.write(resp.read())


def download_media(prop: dict, out_dir: str) -> dict:
    """Download every photo, floorplan, and EPC graphic for a property into
    <out_dir>/<property_id>/{photos,floorplans,epc}/. Returns a summary dict."""
    property_id = prop.get("id")
    prop_dir = os.path.join(out_dir, property_id)
    categories = {
        "photos": (prop.get("images") or [], ".jpeg"),
        "floorplans": (prop.get("floorplans") or [], ".jpeg"),
        "epc": (prop.get("epcGraphs") or [], ".png"),
    }

    counts = {}
    for name, (items, default_ext) in categories.items():
        cat_dir = os.path.join(prop_dir, name)
        os.makedirs(cat_dir, exist_ok=True)
        for i, item in enumerate(items, start=1):
            # Extension must come from the URL's path, not the raw URL
            # string: splitext() on the full URL would sweep a query string
            # (e.g. "?v=3") into the "extension", producing a filename the
            # media-serving route's filename allowlist rejects forever.
            ext = os.path.splitext(urlparse(item["url"]).path)[1] or default_ext
            if not re.fullmatch(r"\.[a-zA-Z0-9]{1,5}", ext):
                ext = default_ext
            dest = os.path.join(cat_dir, f"{i:02d}{ext}")
            download_file(item["url"], dest)
            print(f"{name} {i}/{len(items)} -> {dest}", file=sys.stderr)
        counts[name] = len(items)

    print(
        f"Media done: {counts['photos']} photos, {counts['floorplans']} floorplans, "
        f"{counts['epc']} epc graphs in {prop_dir}",
        file=sys.stderr,
    )
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Rightmove property URL")
    parser.add_argument("-o", "--output", help="Write JSON to this file instead of stdout")
    parser.add_argument(
        "--no-media",
        action="store_true",
        help="Skip downloading photos/floorplans/EPC graphic (downloaded by default)",
    )
    parser.add_argument(
        "--media-dir",
        default="media",
        help="Base directory for downloaded media (default: ./media)",
    )
    parser.add_argument(
        "--no-broadband",
        action="store_true",
        help="Skip fetching broadband speed/deals summary (fetched by default)",
    )
    args = parser.parse_args()

    html = fetch_html(args.url)
    root = resolve_page_model(html)
    prop = root["propertyData"]
    added_on = ((root.get("analyticsInfo") or {}).get("analyticsProperty") or {}).get("added")
    listing = extract_listing(prop, listing_added_on=added_on)

    if not args.no_broadband:
        postcode = f"{listing['postcode_outcode']}{listing['postcode_incode']}"
        try:
            broadband_data = fetch_broadband_summary(postcode)
            listing["broadband"] = summarize_broadband(broadband_data)
        except Exception as e:
            print(f"Broadband fetch failed for {postcode}: {e}", file=sys.stderr)

    if not args.no_media:
        download_media(prop, args.media_dir)

    output = json.dumps(listing, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
