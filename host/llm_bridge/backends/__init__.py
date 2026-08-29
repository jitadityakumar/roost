from llm_bridge.backends.base import BackendError, LlmBackend
from llm_bridge.backends.claude_backend import ClaudeBackend

# Backend-name -> class registry, used by app.py's startup validation to
# construct one singleton instance per distinct name referenced in
# config.BACKENDS_BY_JOB_TYPE. Add a new entry here when a second backend
# (local-LLM, codex, ...) is implemented -- no other code needs to change,
# per issue #73's "per-job-type backend config shape" decision.
REGISTRY: dict[str, type[LlmBackend]] = {
    "claude": ClaudeBackend,
}

__all__ = ["BackendError", "LlmBackend", "ClaudeBackend", "REGISTRY"]
