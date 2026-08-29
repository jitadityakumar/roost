import json
import os

PORT = int(os.environ.get("ROOST_LLM_BRIDGE_PORT", "8094"))

# Absolute path to the claude binary, or a bare name to resolve via PATH.
# Defaults to "claude" (works when PATH already has it, e.g. a manual
# terminal run) but a systemd-launched process needs this pinned explicitly
# -- systemd gives a User= unit its own minimal default PATH, not the login
# shell's, so a bare "claude" silently fails to resolve there even though a
# manual `python -m llm_bridge` smoke test (run from an interactive shell)
# works fine. See roost-llm-bridge.service / README.md.
CLAUDE_BIN = os.environ.get("ROOST_LLM_BRIDGE_CLAUDE_BIN", "claude")

# job_type -> backend name. Every job type defaults to "claude" (today's
# only implementation) -- overridable via env var so routing one job type to
# a future second backend is a config change, not a code change (see issue
# #73's "per-job-type backend config shape" decision).
_DEFAULT_BACKENDS = {"text_extract": "claude", "floor_area_vision": "claude", "epc_vision": "claude"}
BACKENDS_BY_JOB_TYPE = {
    **_DEFAULT_BACKENDS,
    **json.loads(os.environ.get("ROOST_LLM_BRIDGE_BACKENDS", "{}")),
}

# Must byte-for-byte match backend/app/jobs/llm_prompts.py's
# ATTACHED_IMAGE_SENTINEL. Duplicated on purpose, not imported -- the bridge
# must never depend on backend/app/ (see README.md: this is a second,
# independent Python project, kept backend-agnostic and container-
# independent on purpose).
ATTACHED_IMAGE_SENTINEL = "<<ATTACHED_IMAGE>>"

# Defense against an unbounded request body on a no-auth, tailnet-only
# service -- a real Rightmove floorplan/EPC image is nowhere near this size,
# so this is pure headroom, not a real constraint.
MAX_IMAGE_BYTES = 20 * 1024 * 1024
