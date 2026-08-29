from abc import ABC, abstractmethod


class BackendError(Exception):
    """Raised by any LlmBackend.run() failure. `permanent=True` tells the
    bridge's route handler this exact request could never succeed on retry
    (e.g. the backend binary itself is missing) -- mirrors
    llm_client.LlmCallError's `permanent` flag on the container side, which
    is exactly where this maps back to."""

    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


class LlmBackend(ABC):
    @abstractmethod
    def run(
        self,
        prompt: str,
        model: str,
        timeout_s: int,
        allow_read: bool,
        disallow_all_tools: bool,
        json_schema: dict | None,
        image_path: str | None,
    ) -> str:
        """Return the backend's raw stdout (matching what `claude -p` prints
        today) so the container-side parse_structured_output can keep
        parsing it exactly as before. Raise BackendError on any failure; set
        permanent=True only when retrying this exact request could never
        succeed (e.g. the backend binary itself is missing).

        Flag precedence when both allow_read and disallow_all_tools are true
        (today's handlers never actually do this -- vision jobs pass
        allow_read=True/disallow_all_tools=False, text_extract passes the
        reverse -- but the ABC should still say what a future combination
        means): disallow_all_tools wins. It maps to `--disallowedTools "*"`
        (or `--allowedTools StructuredOutput` when a json_schema is also
        given, see ClaudeBackend), which denies Read regardless of
        allow_read -- same precedence today's llm_client.run_claude_prompt
        already has, just made explicit here since a future backend
        implementation has no other spec to go on.

        `model` is Claude-specific vocabulary ("haiku", "sonnet") -- a
        future non-Claude backend either maps it to its own equivalent or
        ignores it; this interface doesn't prescribe which.

        `image_path` is a real filesystem path the bridge has already
        written the (base64-decoded) image bytes to -- see app.py. The
        interface takes a path, not bytes, so a future non-Claude backend
        that also shells out to a CLI doesn't have to re-implement temp-file
        handling."""
        raise NotImplementedError

    def available(self) -> bool:
        """Cheap presence check for /healthz. Not an auth check -- see
        app.py's /healthz docstring for the documented limitation."""
        raise NotImplementedError
