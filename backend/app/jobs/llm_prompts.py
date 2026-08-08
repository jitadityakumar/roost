"""Prompt templates for the three llm-lane job types. First-draft wording,
expected to need iteration once run against real listings (per the 2026-08-08
decision log in context.md) — kept in their own module so they're easy to
find and edit without touching handler logic.
"""

TEXT_EXTRACT_PROMPT = """Below is the free-text description from a UK property listing (HTML tags included as-is). Extract the following fields:

1. "lease_years_remaining": integer years remaining on the lease, or null if freehold / not mentioned.
2. "service_charge_pa": annual service charge in GBP as a number, or null if not mentioned. If only a monthly figure is given, multiply by 12.
3. "council_tax_band": single letter A-H, or null if not mentioned or listed as "TBC".
4. "chain_free": true if explicitly described as chain-free / no onward chain / no forward chain, false if explicitly described as NOT chain-free, null if genuinely unstated. Do not infer from anything else.
5. "cash_only": true if explicitly described as cash buyers only / for cash purchase only, null if unstated. Do not infer from anything else.

Reply with ONLY a JSON object with exactly these five keys, no other text before or after it. Use null (not false or 0) for anything not explicitly stated in the text — do not guess.

Description:
{description}"""

FLOOR_AREA_VISION_PROMPT = """This is a UK property floorplan image at {image_path}. Read the image and find the total floor area as printed on it.

Reply with ONLY a JSON object, no other text before or after it: {{"floor_area_sqm": <number or null>, "floor_area_sqft": <number or null>}}. Populate whichever unit(s) are printed on the image; if only one unit is shown, leave the other null (the caller will convert). If no total floor area figure is printed anywhere on the image, return {{"floor_area_sqm": null, "floor_area_sqft": null}}."""

EPC_VISION_PROMPT = """This is a UK Energy Performance Certificate (EPC) graphic image at {image_path}. Read the image and find the current and potential energy efficiency rating.

Reply with ONLY a JSON object, no other text before or after it: {{"epc_current": "<letter> (<score>)", "epc_potential": "<letter> (<score>)"}}, e.g. {{"epc_current": "C (73)", "epc_potential": "B (80)"}}. Use null for either value if it isn't legible or present on the image. Read the score number carefully off the marker position on the coloured bar — do not guess a score from the letter band alone."""

# JSON schemas passed to `claude -p --output-format json --json-schema ...`
# (see llm_client.run_claude_prompt/parse_structured_output). Prompt wording
# above still asks for the same shape too — the schema constrains the
# model's output at the source, the prompt text is what tells it what each
# field *means*; kept both rather than dropping the in-prompt shape, since
# the schema alone doesn't explain field semantics like "multiply monthly by
# 12" or "do not infer chain_free from anything else".
TEXT_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "lease_years_remaining": {"type": ["integer", "null"]},
        "service_charge_pa": {"type": ["number", "null"]},
        "council_tax_band": {"type": ["string", "null"]},
        "chain_free": {"type": ["boolean", "null"]},
        "cash_only": {"type": ["boolean", "null"]},
    },
    "required": ["lease_years_remaining", "service_charge_pa", "council_tax_band", "chain_free", "cash_only"],
    "additionalProperties": False,
}

FLOOR_AREA_VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "floor_area_sqm": {"type": ["number", "null"]},
        "floor_area_sqft": {"type": ["number", "null"]},
    },
    "required": ["floor_area_sqm", "floor_area_sqft"],
    "additionalProperties": False,
}

EPC_VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "epc_current": {"type": ["string", "null"]},
        "epc_potential": {"type": ["string", "null"]},
    },
    "required": ["epc_current", "epc_potential"],
    "additionalProperties": False,
}
