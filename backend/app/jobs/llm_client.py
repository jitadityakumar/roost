"""Talks to the host-side LLM bridge (host/llm_bridge/, issue #73) for the
three llm-lane job types, and unpacks the structured data back out of its
response into the types the `listings` columns expect — every handler calls
run_claude_prompt + parse_structured_output and gets back a dict of
already-typed values.

The bridge, not this file, is what actually shells out to `claude -p` now —
moved host-resident so token refresh always has read-write access to
`~/.claude` (the container's own `~/.claude` mount was read-only, which is
why llm-lane jobs used to fail permanently during a token-expiry window; see
issue #73). This file only speaks HTTP to it.

Model choice is per-job-type (not global) so one job type can be bumped to a
stronger model without paying for it on the others — see JOB_TYPE_MODELS.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.request

from app.config import LLM_BRIDGE_BASE

logger = logging.getLogger("roost.llm_client")

# Known accuracy risk (see context.md, 2026-08-08 eval): Haiku misread an EPC
# graphic (wrong band and score). Swapping a job type to "sonnet" is a
# one-line change here, not an architecture change, if real-data results
# show the same problem. There is no `effort` knob on Haiku (rejected by the
# API) — the only lever is which model runs.
JOB_TYPE_MODELS = {
    "text_extract": "haiku",
    "floor_area_vision": "haiku",
    "epc_vision": "haiku",
}

TEXT_EXTRACT_TIMEOUT_S = 60
VISION_TIMEOUT_S = 90  # image read + larger output budget than free text


class LlmCallError(RuntimeError):
    """Raised for any failure to get usable structured output back from the
    claude CLI: binary missing, nonzero exit, timeout, or no parseable JSON
    in stdout. Handlers let this propagate — the worker pool's existing
    exception handling (queue.fail_job) already retries/backs off.

    `permanent=True` (e.g. the bridge reports a permanent failure, or
    `ROOST_LLM_BRIDGE_BASE` isn't configured at all) tells the worker pool
    to skip the retry budget entirely — retrying can't fix a config problem
    or a bridge-reported permanent failure, only a human can, so retrying
    just delays a container operator noticing (same reasoning worker.py
    already applies to an unregistered job_type)."""

    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


def bridge_available() -> bool:
    """Calls the bridge's GET /healthz, called once at worker-pool startup
    (see worker.py) so a missing/misconfigured/unreachable bridge shows up
    in `docker logs` immediately at boot, rather than only after the first
    listing gets refreshed and its first llm job fails. Mirrors the old
    cli_available()'s boot-time-check tolerance — a bridge that's down
    should log loudly at boot, not crash the container, so any failure to
    reach it (missing config, connection refused, timeout) returns False
    rather than raising."""
    if not LLM_BRIDGE_BASE:
        return False
    try:
        with urllib.request.urlopen(f"{LLM_BRIDGE_BASE}/healthz", timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


# Kept generous (not the ~500 chars that goes into a job's last_error column,
# which is meant to stay skimmable via the jobs API) because this is the
# only place the *full* failure detail ends up — if something in production
# actually breaks (the exact scenario this logging exists for: an auth
# failure from the mounted ~/.claude session, a CLI version mismatch, an
# unexpected output shape), `docker logs roost` needs to be enough to
# diagnose it without being able to reproduce the failure interactively.
_LOG_TRUNCATE_CHARS = 4000


def run_claude_prompt(
    job_type: str,
    prompt: str,
    model: str,
    timeout_s: int,
    allow_read: bool = False,
    json_schema: dict | None = None,
    disallow_all_tools: bool = False,
    image_bytes: bytes | None = None,
    image_suffix: str | None = None,
) -> str:
    """POST to the host-side LLM bridge's `/v1/llm/<job_type>` and return its
    raw `stdout` field (matching what a local `claude -p` call used to
    return directly, before issue #73 moved the actual CLI invocation
    host-side) — everything downstream (parse_structured_output etc.) is
    unchanged.

    `job_type` picks both the bridge route and (bridge-side) which backend
    config to use for this call — always one of "text_extract",
    "floor_area_vision", "epc_vision".

    `allow_read` grants the Read tool (only needed by the vision jobs, which
    point it at an image path embedded in the prompt via the sentinel — see
    llm_prompts.ATTACHED_IMAGE_SENTINEL) — text_extract has nothing to read
    and gets no tool access, since its prompt embeds attacker-influenced
    text (a Rightmove listing description) and there's no reason to hand
    that a filesystem-reading tool.

    `json_schema`, when given, adds `--output-format json --json-schema
    <schema>` bridge-side so the CLI validates the model's output against
    the schema at the source (see parse_structured_output for how the
    resulting envelope is unpacked) instead of relying solely on prompt
    wording + tolerant parsing.

    `disallow_all_tools` denies all tool access. Omitting `--allowedTools
    Read` alone does NOT block file reads — confirmed empirically that the
    model can still read files via the CLI's hardcoded always-on read-only
    Bash commands (`cat`, `head`, etc.) even with no tools explicitly
    allowed. Used by text_extract, whose prompt embeds attacker-influenced
    text and has no legitimate reason to touch the filesystem at all.

    `image_bytes`/`image_suffix`: the vision handlers pass the actual image
    file's bytes and its on-disk suffix (e.g. ".jpg") explicitly — the
    bridge base64-decodes them into its own temp file and substitutes that
    path for the sentinel in the prompt before invoking its backend. Sent as
    base64 in the JSON body (not a file path) so this still works even if
    the container and the bridge never share a filesystem/mount."""
    if not LLM_BRIDGE_BASE:
        raise LlmCallError(
            "ROOST_LLM_BRIDGE_BASE is not set -- the LLM bridge's address must be "
            "configured via environment variable, see CLAUDE.md",
            permanent=True,
        )

    body = {
        "prompt": prompt,
        "model": model,
        "timeout_s": timeout_s,
        "allow_read": allow_read,
        "disallow_all_tools": disallow_all_tools,
        "json_schema": json_schema,
        "image_base64": base64.b64encode(image_bytes).decode("ascii") if image_bytes is not None else None,
        "image_suffix": image_suffix,
    }
    url = f"{LLM_BRIDGE_BASE}/v1/llm/{job_type}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # The bridge already enforces timeout_s for the backend subprocess call
    # itself; this HTTP-level timeout just needs a margin so it doesn't fire
    # first and race the bridge's own timeout handling.
    try:
        with urllib.request.urlopen(req, timeout=timeout_s + 10) as resp:
            response_body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # HTTPError is raised for any non-2xx response -- it is not a
        # response object you can just check .status on. Must be caught
        # before the generic URLError below (HTTPError is a subclass of it).
        try:
            error_body = json.loads(e.read())
            message = error_body.get("error", str(e))
            permanent = bool(error_body.get("permanent"))
        except (ValueError, json.JSONDecodeError):
            message, permanent = str(e), False
        logger.warning("LLM bridge request failed (job_type=%s): %s", job_type, message)
        raise LlmCallError(f"bridge request failed: {message}", permanent=permanent) from e
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning("LLM bridge unreachable (job_type=%s): %s", job_type, e)
        raise LlmCallError(f"bridge unreachable: {e}", permanent=False) from e

    return response_body["stdout"]


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_block(raw_output: str) -> dict:
    """The CLI's text output isn't guaranteed to be pure JSON even when the
    prompt asks for 'only JSON' — it may wrap it in a code fence or add a
    stray sentence. Try increasingly permissive parses: the stripped output
    as-is, then with a ```/```json fence stripped, then a best-effort regex
    span as a last resort (which can misfire if the output ever contains two
    JSON objects or a brace inside prose — kept as the final fallback, not
    the first attempt, for that reason)."""
    stripped = raw_output.strip()
    for candidate in (stripped, _strip_code_fence(stripped)):
        if candidate is None:
            continue
        try:
            result = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            return result

    match = _JSON_BLOCK_RE.search(raw_output)
    if match:
        try:
            result = json.loads(match.group(0))
        except json.JSONDecodeError:
            result = None
        if isinstance(result, dict):
            return result

    logger.warning("no parseable JSON object in claude output: %s", raw_output[:_LOG_TRUNCATE_CHARS])
    raise LlmCallError(f"no parseable JSON object in claude output: {raw_output[:500]!r}")


def _strip_code_fence(text: str) -> str | None:
    if not text.startswith("```"):
        return None
    body = text[3:]
    if body.startswith("json"):
        body = body[4:]
    end = body.rfind("```")
    return body[:end].strip() if end != -1 else None


def parse_structured_output(raw_output: str) -> dict:
    """Unpacks the envelope `claude -p --output-format json --json-schema
    ...` returns (see run_claude_prompt). Empirically confirmed shape (real
    API call, 2026-08-08): {"type":"result","subtype":"success",
    "is_error":bool,"result":"<text, still ```json-fenced even with this
    flag>","structured_output":<schema-validated data, when present>,
    "total_cost_usd":float,"duration_ms":int,...}. Prefers
    `structured_output` (the actual schema-validated field) but falls back
    to tolerantly parsing `result` via extract_json_block, in case a given
    CLI version/response doesn't populate structured_output for some
    reason — keeps the same resilience the free-text path already had
    rather than trading it away for the schema feature."""
    try:
        envelope = json.loads(raw_output)
    except json.JSONDecodeError as e:
        logger.warning(
            "claude --output-format json produced an unparseable envelope: %s",
            raw_output[:_LOG_TRUNCATE_CHARS],
        )
        raise LlmCallError(f"unparseable claude JSON envelope: {raw_output[:500]!r}") from e

    if not isinstance(envelope, dict):
        raise LlmCallError(f"claude JSON envelope was not an object: {raw_output[:500]!r}")

    # Logged before the is_error check (not just on the success path) — a
    # failed call still accrues real cost, and that's exactly the kind of
    # thing `docker logs roost` needs to show for diagnosability.
    logger.info(
        "claude -p structured call: cost=$%.4f duration=%dms",
        envelope.get("total_cost_usd") or 0.0,
        envelope.get("duration_ms") or 0,
    )

    if envelope.get("is_error"):
        message = str(envelope.get("result"))[:500]
        raise LlmCallError(f"claude reported is_error for this call: {message}")

    structured_output = envelope.get("structured_output")
    if isinstance(structured_output, dict):
        return structured_output

    return extract_json_block(envelope.get("result") or "")


# Matches the first run of digits in a string, tolerating thousands commas
# inside the run (so "1,250" and "approx. 1,250 sq ft" both find "1,250",
# not just the "1" or the "." in "approx."), plus an optional decimal part.
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _parse_numeric_string(value: str) -> float | None:
    match = _NUMBER_RE.search(value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def as_int(value) -> int | None:
    """Accepts a real int/float or a numeric string; anything else (a
    sentence with no digits, etc.) is treated as absent rather than crashing
    the job on a coercion error. Tolerant of currency/unit text around the
    number ('£1,200 p.a.', 'approx. 1,250 sq ft')."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(value)
    if isinstance(value, str):
        parsed = _parse_numeric_string(value)
        return round(parsed) if parsed is not None else None
    return None


def as_float(value) -> float | None:
    """Same permissiveness as as_int but keeps decimal precision, for
    floor_area_sqft (a REAL column)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return _parse_numeric_string(value)
    return None


def as_bool(value) -> bool | None:
    """Only a real bool, or the strings 'true'/'false' (case-insensitive),
    count — a truthy-but-wrong string like 'no' or 'false' must not
    silently coerce to True via a bare bool(value) call."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


# Official England & Wales EPC band thresholds (gov.uk): A 92+, B 81-91,
# C 69-80, D 55-68, E 39-54, F 21-38, G 1-20 — sorted descending so the
# first threshold a score meets or exceeds is its band.
_EPC_BAND_THRESHOLDS = [
    (92, "A"),
    (81, "B"),
    (69, "C"),
    (55, "D"),
    (39, "E"),
    (21, "F"),
    (1, "G"),
]


def epc_band_for_score(score: int) -> str | None:
    """The app calculates the letter band from the numeric score itself,
    rather than trusting the model's letter — a misread band is a bigger
    error than a misread number, and the two should never be allowed to
    disagree. Found on a real (non-synthetic) listing on 2026-08-08: Haiku
    correctly read a score of 81 off a real EPC graphic but misclassified
    it as band A (should be B) — the prompt/schema now only asks for the
    score, not the letter, and this function is the source of truth for
    the band."""
    for threshold, band in _EPC_BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return None  # a score below 1 isn't a valid EPC score


def epc_rating_from_score(value) -> str | None:
    """Coerces `value` via as_int, then formats as '<Letter> (<score>)'
    using epc_band_for_score. None if the score doesn't coerce or is out of
    the valid EPC range (1-100-ish; epc_band_for_score returns None below
    1, and a hallucinated >100 score is still shown since there's no
    documented upper cap worth guessing at)."""
    score = as_int(value)
    if score is None:
        return None
    band = epc_band_for_score(score)
    if band is None:
        return None
    return f"{band} ({score})"


_BAND_RE = re.compile(r"^[A-H]$")


def as_council_tax_band(value) -> str | None:
    if not isinstance(value, str):
        return None
    band = value.strip().upper()
    if not band or band == "TBC" or not _BAND_RE.match(band):
        return None
    return band
