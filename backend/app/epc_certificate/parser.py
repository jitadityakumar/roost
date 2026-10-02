"""Deterministic parser for a gov.uk "Find an energy certificate" page
(issue #115). Pure function, no I/O -- see client.py for the fetch.

Anchored on the page's stable ids/classes rather than text position. Every
field except the address and the current rating/score is optional: an older
or unusual certificate that lacks one (e.g. no "Potential rating" for a
step, "N/A" feature ratings) must still parse. Deliberately never reads the
"Who to contact" assessor name/phone/email (personal data, not stored).
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup


class CertificateParseError(ValueError):
    pass


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _int(s: str | None) -> int | None:
    if not s:
        return None
    m = re.search(r"-?[\d,]+", s)
    return int(m.group(0).replace(",", "")) if m else None


def _float(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"-?[\d,]*\.?\d+", s)
    return float(m.group(0).replace(",", "")) if m else None


def _iso_date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def _dl_value(root, label: str):
    """The <dd> text for the <dt> whose text starts with `label`."""
    if root is None:
        return None
    for dt in root.find_all("dt"):
        if _text(dt).lower().startswith(label.lower()):
            dd = dt.find_next_sibling("dd")
            return dd
    return None


def _ratings_from_desc(soup) -> dict:
    desc = soup.find(id="svg-desc")
    text = _text(desc)
    cur = re.search(r"energy rating is ([A-G]) with a score of (\d+)", text)
    pot = re.search(r"potential energy rating of ([A-G]) with a score of (\d+)", text)
    return {
        "current_rating": cur.group(1) if cur else None,
        "current_score": int(cur.group(2)) if cur else None,
        "potential_rating": pot.group(1) if pot else None,
        "potential_score": int(pot.group(2)) if pot else None,
    }


def _features(soup) -> list[dict]:
    section = soup.find(id="summary")
    table = section.find("table") if section else None
    out = []
    if table is None:
        return out
    for tr in table.find_all("tr"):
        th = tr.find("th")
        tds = tr.find_all("td")
        if th is None or len(tds) < 2:
            continue
        out.append({"feature": _text(th), "description": _text(tds[0]), "rating": _text(tds[1])})
    return out


def _steps(soup) -> list[dict]:
    out = []
    for block in soup.select(".epb-recommended-improvements"):
        h3 = block.find("h3")
        m = re.match(r"Step\s+(\d+):\s*(.+)", _text(h3))
        if not m:
            continue
        cost = _text(_dl_value(block, "Typical installation cost"))
        saving = _text(_dl_value(block, "Typical yearly saving"))
        potential = _text(_dl_value(block, "Potential rating"))
        out.append(
            {
                "step": int(m.group(1)),
                "title": m.group(2).strip(),
                "installation_cost": cost or None,
                "yearly_saving_gbp": _int(saving),
                "potential_rating": potential or None,
            }
        )
    return out


def parse_certificate(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    addr_node = soup.select_one("p.epc-address")
    if addr_node is None:
        raise CertificateParseError("no address found -- not an EPC certificate page?")
    lines = [re.sub(r"\s+", " ", s).strip() for s in addr_node.stripped_strings]
    lines = [ln for ln in lines if ln]
    address = ", ".join(lines)
    postcode = lines[-1] if lines else None

    ratings = _ratings_from_desc(soup)
    if ratings["current_rating"] is None or ratings["current_score"] is None:
        raise CertificateParseError("could not read the energy rating/score")

    extra = {}
    for box in soup.select(".epc-extra-box"):
        label = _text(box.find("label"))
        value = _text(box.find("p"))
        extra[label.lower()] = value

    summary = {}
    for row in soup.select(".epc-box-container dl.govuk-summary-list .govuk-summary-list__row"):
        summary[_text(row.find("dt")).lower()] = _text(row.find("dd"))

    info = soup.find(id="information")
    assessment_type_dd = _dl_value(info, "Type of assessment")
    assessment_type = None
    if assessment_type_dd is not None:
        label = assessment_type_dd.select_one(".govuk-details__summary-text")
        if label:
            for hidden in label.select(".govuk-visually-hidden"):
                hidden.extract()
            assessment_type = _text(label) or None

    bills = soup.find(id="bills-affected")
    bills_text = _text(bills)
    cost = re.search(r"£([\d,]+) per year on heating, hot water and lighting", bills_text)
    saving = re.search(r"save £([\d,]+) per year", bills_text)
    basis = re.search(r"based on average costs in (\d{4})", bills_text)
    heating = re.search(r"([\d,]+) kWh per year for heating", bills_text)
    hot_water = re.search(r"([\d,]+) kWh per year for hot water", bills_text)

    primary = soup.find(id="summary")
    primary_match = re.search(r"per year is ([\d,]+) kilowatt hours per square metre", _text(primary))

    return {
        "certificate_number": extra.get("certificate number") or None,
        "address": address,
        "postcode": postcode,
        **ratings,
        "valid_until": _iso_date(extra.get("valid until")),
        "assessment_date": _iso_date(_text(_dl_value(info, "Date of assessment"))),
        "certificate_date": _iso_date(_text(_dl_value(info, "Date of certificate"))),
        "assessment_type": assessment_type,
        "property_type": summary.get("property type") or None,
        "total_floor_area_sqm": _float(summary.get("total floor area")),
        "primary_energy_kwh_m2": _int(primary_match.group(1)) if primary_match else None,
        "estimated_annual_cost_gbp": _int(cost.group(1)) if cost else None,
        "potential_saving_gbp": _int(saving.group(1)) if saving else None,
        "cost_basis_year": int(basis.group(1)) if basis else None,
        "heating_kwh_per_year": _int(heating.group(1)) if heating else None,
        "hot_water_kwh_per_year": _int(hot_water.group(1)) if hot_water else None,
        "co2_current_tonnes": _float(_text(soup.find(id="eir-property-produces"))),
        "co2_potential_tonnes": _float(_text(soup.find(id="eir-potential-production"))),
        "features": _features(soup),
        "steps": _steps(soup),
    }
