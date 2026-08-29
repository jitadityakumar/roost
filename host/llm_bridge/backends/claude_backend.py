"""Wraps `claude -p`, host-resident. This is today's only backend -- moved
almost verbatim from the container's old `app/jobs/llm_client.py::
run_claude_prompt` (see that file's git history), with LlmCallError renamed
to BackendError. Runs with the invoking user's (jkumar's) normal read-write
`~/.claude`, so token refresh Just Works here -- no special handling needed,
which is the entire point of issue #73's host-side bridge.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess

from llm_bridge.backends.base import BackendError, LlmBackend
from llm_bridge.config import ATTACHED_IMAGE_SENTINEL, CLAUDE_BIN

logger = logging.getLogger("llm_bridge.claude_backend")

# Same reasoning as the old container-side llm_client.py: the truncated
# ~500-char message that ends up in a container's DB error column isn't
# enough to diagnose a real failure (auth error, CLI version mismatch) --
# the bridge's own log needs the full detail.
_LOG_TRUNCATE_CHARS = 4000


class ClaudeBackend(LlmBackend):
    def available(self) -> bool:
        return shutil.which(CLAUDE_BIN) is not None

    def run(
        self,
        prompt: str,
        model: str,
        timeout_s: int,
        allow_read: bool = False,
        disallow_all_tools: bool = False,
        json_schema: dict | None = None,
        image_path: str | None = None,
    ) -> str:
        # The route handler (app.py) already validated that a sentinel and
        # an image_path are given together or not at all -- here it's just
        # a plain string substitution before the real path ever reaches
        # `claude -p`. Doesn't touch the sentinel constant's producer
        # (llm_prompts.py on the container side) at all.
        if image_path is not None:
            prompt = prompt.replace(ATTACHED_IMAGE_SENTINEL, image_path)

        argv = [CLAUDE_BIN, "-p", prompt, "--model", model]
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
            raise BackendError(f"claude -p timed out after {timeout_s}s") from e
        except FileNotFoundError as e:
            logger.error(
                "claude binary (%s) not found -- check ROOST_LLM_BRIDGE_CLAUDE_BIN / PATH", CLAUDE_BIN
            )
            raise BackendError(f"claude binary ({CLAUDE_BIN}) not found", permanent=True) from e

        if result.returncode != 0:
            logger.warning(
                "claude -p (model=%s) exited %d\nstderr: %s\nstdout: %s",
                model,
                result.returncode,
                result.stderr.strip()[:_LOG_TRUNCATE_CHARS],
                result.stdout.strip()[:_LOG_TRUNCATE_CHARS],
            )
            raise BackendError(f"claude -p exited {result.returncode}: {result.stderr.strip()[:500]}")
        return result.stdout
