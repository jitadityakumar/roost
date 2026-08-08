"""Wraps shelling out to the `claude` CLI (Claude Code, non-interactive mode)
for the three llm-lane job types. This is the only place that knows the CLI's
argv shape, how to get structured data back out of its free-form stdout, and
how to coerce that data into the types the `listings` columns expect — every
handler calls run_claude_prompt + parse_structured_output and gets back a
dict of already-typed values.

Model choice is per-job-type (not global) so one job type can be bumped to a
stronger model without paying for it on the others — see JOB_TYPE_MODELS.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess

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

    `permanent=True` (currently only set when the `claude` binary itself is
    missing) tells the worker pool to skip the retry budget entirely — a
    missing binary can't be fixed by retrying the same job 3 times, only by
    fixing the container, so retrying just delays a container operator
    noticing (same reasoning worker.py already applies to an unregistered
    job_type)."""

    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


def cli_available() -> bool:
    """Cheap PATH check, called once at worker-pool startup (see worker.py)
    so a missing/misconfigured CLI shows up in `docker logs` immediately at
    boot, rather than only after the first listing gets refreshed and its
    first llm job fails."""
    return shutil.which("claude") is not None


# Kept generous (not the ~500 chars that goes into a job's last_error column,
# which is meant to stay skimmable via the jobs API) because this is the
# only place the *full* failure detail ends up — if something in production
# actually breaks (the exact scenario this logging exists for: an auth
# failure from the mounted ~/.claude session, a CLI version mismatch, an
# unexpected output shape), `docker logs roost` needs to be enough to
# diagnose it without being able to reproduce the failure interactively.
_LOG_TRUNCATE_CHARS = 4000


def run_claude_prompt(
    prompt: str,
    model: str,
    timeout_s: int,
    allow_read: bool = False,
    json_schema: dict | None = None,
    disallow_all_tools: bool = False,
) -> str:
    """Invoke `claude -p <prompt> --model <model>` non-interactively and
    return raw stdout. `allow_read` grants the Read tool (only needed by the
    vision jobs, which point it at an image path embedded in the prompt) —
    text_extract has nothing to read and gets no tool access, since its
    prompt embeds attacker-influenced text (a Rightmove listing description)
    and there's no reason to hand that a filesystem-reading tool.

    `json_schema`, when given, adds `--output-format json --json-schema
    <schema>` so the CLI validates the model's output against the schema at
    the source (see parse_structured_output for how the resulting envelope
    is unpacked) instead of relying solely on prompt wording + tolerant
    parsing.

    `disallow_all_tools` denies all tool access. Omitting `--allowedTools
    Read` alone does NOT block file reads — confirmed empirically that the
    model can still read files via the CLI's hardcoded always-on read-only
    Bash commands (`cat`, `head`, etc.) even with no tools explicitly
    allowed. Used by text_extract, whose prompt embeds attacker-influenced
    text and has no legitimate reason to touch the filesystem at all.

    When `json_schema` is also given, this is implemented as `--allowedTools
    StructuredOutput` rather than `--disallowedTools "*"`. Confirmed
    empirically that `--disallowedTools "*"` also denies the CLI's own
    internal `StructuredOutput` tool — the mechanism `--json-schema` output
    actually goes through — which breaks schema output entirely (the model
    calls StructuredOutput, gets denied twice, then gives up with no usable
    result). `--allowedTools <name>` is an allowlist, so naming only
    StructuredOutput still implicitly denies everything else (Bash, Read,
    etc.) — confirmed empirically it still blocks a prompt-injected `cat`
    attempt, same as `--disallowedTools "*"` did."""
    argv = ["claude", "-p", prompt, "--model", model]
    if allow_read:
        argv += ["--allowedTools", "Read"]
    if disallow_all_tools:
        if json_schema is not None:
            argv += ["--allowedTools", "StructuredOutput"]
        else:
            argv += ["--disallowedTools", "*"]
    if json_schema is not None:
        argv += ["--output-format", "json", "--json-schema", json.dumps(json_schema)]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        logger.warning("claude -p (model=%s) timed out after %ds", model, timeout_s)
        raise LlmCallError(f"claude -p timed out after {timeout_s}s") from e
    except FileNotFoundError as e:
        logger.error(
            "claude CLI not found on PATH — check the Dockerfile installed it and it's "
            "actually on this container's PATH"
        )
        raise LlmCallError(
            "claude CLI not found on PATH — see Dockerfile / README 'Running with Docker'",
            permanent=True,
        ) from e
    if result.returncode != 0:
        # Deliberately logged in full (not just the truncated message that
        # ends up in the DB) — an auth failure from the mounted ~/.claude
        # session is exactly the kind of thing whose real explanation is a
        # sentence or two in stderr that a 500-char truncation could cut off.
        logger.warning(
            "claude -p (model=%s) exited %d\nstderr: %s\nstdout: %s",
            model,
            result.returncode,
            result.stderr.strip()[:_LOG_TRUNCATE_CHARS],
            result.stdout.strip()[:_LOG_TRUNCATE_CHARS],
        )
        raise LlmCallError(f"claude -p exited {result.returncode}: {result.stderr.strip()[:500]}")
    return result.stdout


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


_EPC_RE = re.compile(r"\b([A-G])\b(?:\s*\((\d+)\))?", re.I)


def as_epc_rating(value) -> str | None:
    """Normalizes to '<Letter> (<score>)', or just '<Letter>' if no score is
    present. Accepts a plain string ('C (73)', 'C') or a {'letter', 'score'}
    dict shape, in case the model ever returns that instead."""
    if isinstance(value, dict):
        letter = value.get("letter")
        score = value.get("score")
        text = f"{letter} ({score})" if letter and score is not None else letter
    elif isinstance(value, str):
        text = value
    else:
        return None
    if not text:
        return None
    match = _EPC_RE.search(text)
    if not match:
        return None
    letter, score = match.group(1).upper(), match.group(2)
    return f"{letter} ({score})" if score else letter


_BAND_RE = re.compile(r"^[A-H]$")


def as_council_tax_band(value) -> str | None:
    if not isinstance(value, str):
        return None
    band = value.strip().upper()
    if not band or band == "TBC" or not _BAND_RE.match(band):
        return None
    return band
