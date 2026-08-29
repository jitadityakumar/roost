"""Roost LLM bridge -- a small host-resident HTTP service the Roost
container calls out to for the three llm-lane job types (text_extract,
floor_area_vision, epc_vision), instead of shelling out to `claude -p`
locally inside the container. See issue #73: the container's `~/.claude`
mount is read-only, so a token refresh triggered inside the container can
never be persisted back to the host; this bridge runs host-resident (normal
read-write `~/.claude`) so refresh always works.

**Concurrency**: Roost's LlmLaneWorkerPool (backend/app/jobs/worker.py) is
already strictly serial -- confirmed in the issue -- the container never
fires two llm-lane jobs concurrently today. So this bridge needs no internal
queue/lock of its own for v1. A future second caller of the bridge, or a
Roost concurrency change, would need to revisit this. One edge case this
doesn't fully cover: if the container-side HTTP timeout fires before this
bridge's own timeout_s deadline on the backend subprocess, the container
will retry while the bridge is still finishing (and killing) the original
`claude` subprocess -- a brief window where two processes exist despite the
"serial" assumption. Harmless in practice (the orphaned one is already being
torn down) but worth this note so nobody "fixes" it as a bug later.

No auth, no TLS -- binds 0.0.0.0 unconditionally, relying on this host's
firewall (default-deny-incoming, only tailscale0 allowed in, plus an
explicit docker0-scoped rule for this port) as the actual access control.
Accepted tradeoff for a single-user tailnet, see issue #73.
"""
from __future__ import annotations

import base64
import logging
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from llm_bridge.backends import REGISTRY, BackendError
from llm_bridge.config import ATTACHED_IMAGE_SENTINEL, BACKENDS_BY_JOB_TYPE, MAX_IMAGE_BYTES

logger = logging.getLogger("llm_bridge.app")

app = FastAPI()


def _error_response(status_code: int, message: str, permanent: bool) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message, "permanent": permanent})


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Never let FastAPI's default {"detail": [...]} shape leak through -- the
    # container's error parser only understands {"error", "permanent"} and
    # must not crash on an unrecognized shape. A malformed request body is a
    # Roost/bridge contract violation, not a transient condition.
    return _error_response(400, str(exc), True)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # FastAPI/Starlette's own 404 (unknown path) and 405 (wrong method) responses
    # go through this handler, not the generic Exception one below or
    # RequestValidationError -- without this, they'd leak the default
    # {"detail": "..."}-shaped body. Concretely: a misconfigured
    # ROOST_LLM_BRIDGE_BASE with a trailing slash produces a double-slash
    # request path that 404s here; without this handler the container's error
    # parser can't find "error"/"permanent" in the body, defaults to
    # permanent=False, and retries a request that can never succeed. A 404/405
    # here is itself a permanent condition (retrying the identical request
    # can't fix a wrong path/method), so `permanent=True`.
    return _error_response(exc.status_code, str(exc.detail), True)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled exception in %s %s", request.method, request.url.path)
    return _error_response(500, str(exc), False)


# Built once at startup (after config validation below), reused across
# requests -- there's no per-request state (ClaudeBackend just shells out
# fresh each call).
_backend_instances: dict[str, object] = {}


def _build_backends() -> None:
    for job_type, backend_name in BACKENDS_BY_JOB_TYPE.items():
        if backend_name not in REGISTRY:
            raise RuntimeError(
                f"unknown backend {backend_name!r} configured for job_type {job_type!r} -- "
                f"check ROOST_LLM_BRIDGE_BACKENDS, valid names: {sorted(REGISTRY)}"
            )
    for backend_name in set(BACKENDS_BY_JOB_TYPE.values()):
        _backend_instances[backend_name] = REGISTRY[backend_name]()


_build_backends()


def _backend_for_job_type(job_type: str):
    backend_name = BACKENDS_BY_JOB_TYPE.get(job_type)
    if backend_name is None:
        return None
    return _backend_instances[backend_name]


class LlmRequest(BaseModel):
    prompt: str
    model: str
    timeout_s: int
    allow_read: bool = False
    disallow_all_tools: bool = False
    json_schema: dict | None = None
    image_base64: str | None = None
    image_suffix: str | None = None


@app.get("/healthz")
def healthz():
    """{"ok": true} if every configured backend reports available (binary
    present), else 503. **Limitation, not a bug**: `available()` is a
    binary-presence check (shutil.which), not an auth check -- it returns
    True even during exactly the expired-OAuth-token window issue #73 is
    about. A deeper check (an actual trial `claude -p` call) is deliberately
    out of scope for v1 -- expensive to run on every container boot. A
    manual/cron `?deep=1` variant would be the natural follow-up if this
    bites in practice.

    Plain `def`, not `async def`: backend.available() can shell out
    (shutil.which is cheap, but a future backend's equivalent might not be)
    and FastAPI runs plain `def` routes in its threadpool automatically,
    which matters more for POST /v1/llm/{job_type} below but is kept
    consistent here too."""
    ok = all(b.available() for b in _backend_instances.values())
    if not ok:
        return JSONResponse(status_code=503, content={"ok": False})
    return {"ok": True}


@app.post("/v1/llm/{job_type}")
def run_llm(job_type: str, body: LlmRequest):
    """Plain `def`, not `async def` -- backend.run() is a blocking
    subprocess.run call that can take up to timeout_s (60-90s). An
    `async def` route runs directly on FastAPI's single event loop, so a
    blocking call in one would freeze /healthz and every other request for
    the call's full duration; a plain `def` route runs in FastAPI's
    threadpool automatically."""
    backend = _backend_for_job_type(job_type)
    if backend is None:
        return _error_response(400, f"unknown job_type {job_type!r}", True)

    has_image = body.image_base64 is not None
    sentinel_in_prompt = ATTACHED_IMAGE_SENTINEL in body.prompt
    if has_image and not sentinel_in_prompt:
        return _error_response(
            400, f"image_base64 given but prompt has no {ATTACHED_IMAGE_SENTINEL} sentinel", True
        )
    if not has_image and sentinel_in_prompt:
        return _error_response(
            400, f"prompt has {ATTACHED_IMAGE_SENTINEL} sentinel but image_base64 was not given", True
        )
    if has_image and not body.image_suffix:
        return _error_response(400, "image_base64 given but image_suffix missing", True)
    # image_suffix reaches tempfile.NamedTemporaryFile(suffix=...) below --
    # a value like "/../../tmp/evil" would still be blocked by the OS
    # (ENOENT/ENOTDIR, since the base temp dir component it's appended to
    # doesn't exist along that path), but it hits the generic exception
    # handler and comes back as a 500 with permanent=False, so the
    # container retries a request that can never succeed, and the raw OS
    # error (a real host filesystem path) gets echoed back to the caller.
    # Restrict to a plain file extension up front instead.
    if has_image and not re.fullmatch(r"\.[A-Za-z0-9]{1,8}", body.image_suffix):
        return _error_response(400, "image_suffix must be a simple file extension, e.g. '.jpg'", True)

    image_path = None
    tmp_file = None
    try:
        if has_image:
            # Reject on encoded length before the more expensive b64decode
            # allocates a second full copy -- this is a no-auth service
            # reachable by any container on the host, so an oversized body
            # should be rejected as cheaply as possible rather than fully
            # decoded first. Base64 expands ~4/3, so this is a conservative
            # upper bound on the decoded size, not an exact one.
            if len(body.image_base64) > MAX_IMAGE_BYTES * 4 // 3 + 4:
                return _error_response(400, "image_base64 exceeds the maximum allowed size", True)
            try:
                image_bytes = base64.b64decode(body.image_base64, validate=True)
            except Exception as e:
                return _error_response(400, f"image_base64 is not valid base64: {e}", True)
            if len(image_bytes) > MAX_IMAGE_BYTES:
                return _error_response(400, "image_base64 exceeds the maximum allowed size", True)
            tmp_file = tempfile.NamedTemporaryFile(suffix=body.image_suffix, delete=False)
            tmp_file.write(image_bytes)
            tmp_file.close()
            image_path = tmp_file.name

        try:
            stdout = backend.run(
                prompt=body.prompt,
                model=body.model,
                timeout_s=body.timeout_s,
                allow_read=body.allow_read,
                disallow_all_tools=body.disallow_all_tools,
                json_schema=body.json_schema,
                image_path=image_path,
            )
        except BackendError as e:
            return _error_response(502, str(e), e.permanent)

        return {"stdout": stdout}
    finally:
        if tmp_file is not None:
            Path(tmp_file.name).unlink(missing_ok=True)
