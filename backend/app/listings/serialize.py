import json


def _norm_postcode(pc: str | None) -> str:
    return "".join((pc or "").split()).upper()


def _attach_epc_certificate(out: dict) -> None:
    """Issue #115: expose the parsed certificate as `epc_certificate`
    (None until the fetch job succeeds), the raw JSON column is dropped.
    `display_address` is the certificate's full address when one is attached
    (the true address -- Rightmove's is usually partial), else Rightmove's.
    `postcode_mismatch` flags a likely wrong-certificate paste; it's only
    set when both postcodes are known."""
    raw = out.pop("epc_certificate_data", None)
    cert = None
    if raw:
        try:
            cert = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            cert = None
    if cert is not None:
        listing_pc, cert_pc = _norm_postcode(out.get("postcode")), _norm_postcode(cert.get("postcode"))
        # Only compare full postcodes (>= 5 chars: outcode + 3-char incode);
        # a partial one like "AB1" would always look like a mismatch.
        cert["postcode_mismatch"] = len(listing_pc) >= 5 and len(cert_pc) >= 5 and listing_pc != cert_pc
    out["epc_certificate"] = cert
    if cert is not None:
        out["epc_source"] = "certificate"  # not a stored value, see epc_certificate/store.py
    out["display_address"] = (cert or {}).get("address") or out.get("address")


def serialize_listing(row: dict) -> dict:
    out = dict(row)
    for field in ("key_features", "nearest_stations_raw", "edited_fields"):
        if out.get(field):
            try:
                out[field] = json.loads(out[field])
            except (TypeError, json.JSONDecodeError):
                pass
    if out.get("rightmove_status"):
        try:
            out["rightmove_status"] = json.loads(out["rightmove_status"])
        except (TypeError, json.JSONDecodeError):
            pass
    _attach_epc_certificate(out)
    for bool_field in ("chain_free", "cash_only", "garden"):
        if out.get(bool_field) is not None:
            out[bool_field] = bool(out[bool_field])
    return out
