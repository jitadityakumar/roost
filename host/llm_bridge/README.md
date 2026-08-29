# Roost LLM bridge

A small host-resident HTTP service the Roost container calls out to for its
three `llm`-lane job types (`text_extract`, `floor_area_vision`,
`epc_vision`), instead of shelling out to `claude -p` inside the container.
See [issue #73](https://github.com/jitadityakumar/roost/issues/73): the
container's old `~/.claude` mount was read-only, so a token refresh
triggered inside the container could never be persisted back to the host,
causing llm-lane jobs to fail permanently during any token-expiry window.
This bridge runs as a normal (non-root) host user with ordinary read-write
access to `~/.claude`, so refresh just works.

This is a **second, independent Python project** living inside the Roost
repo — its own venv and `requirements.txt`, not a package under
`backend/app/`. It must never import anything from `backend/app/` — that's
what keeps it backend-agnostic (a future non-Claude backend needs no Roost
knowledge) and container-independent.

## Setup (manual, human-run — not part of `docker build`/`docker run`)

From `host/llm_bridge/`:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `host/llm_bridge/.env` (gitignored, host-specific, mirrors the
container's own `.env` precedent). Nothing is required for the default
all-Claude config — every var below is an optional override:

```
ROOST_LLM_BRIDGE_PORT=8094
# Pin this to the claude binary's absolute path (`which claude` in your
# login shell) -- a systemd User= unit does NOT inherit your login shell's
# PATH, so a bare "claude" that works fine in a manual terminal run will
# silently fail to resolve when launched by systemd. See config.py.
ROOST_LLM_BRIDGE_CLAUDE_BIN=/absolute/path/to/claude
# Only needed to route a specific job_type to a non-default backend, e.g.
# ROOST_LLM_BRIDGE_BACKENDS={"text_extract": "codex"}
```

Smoke test manually before touching systemd:

```
cd host/llm_bridge
source .venv/bin/activate
set -a; source .env; set +a
python -m llm_bridge
# in another terminal:
curl -s localhost:8094/healthz
```

## Installing as a systemd unit (autostart on boot)

```
sudo cp host/llm_bridge/roost-llm-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now roost-llm-bridge
sudo systemctl status roost-llm-bridge
```

`roost-llm-bridge.service` pulls its env from `host/llm_bridge/.env` via
`EnvironmentFile=` — edit the placeholder `User=`/path values in the unit
file to match your actual host user and clone location before installing,
and make sure `ROOST_LLM_BRIDGE_CLAUDE_BIN` is set to an absolute path there
(see above — this bites silently otherwise, since a manual run from an
interactive shell won't reproduce the PATH difference).

## Container → host network path

The Roost container needs `--add-host=host.docker.internal:host-gateway` on
its `docker run` (see the repo root `Dockerfile` / `CLAUDE.md`) plus
`ROOST_LLM_BRIDGE_BASE=http://host.docker.internal:8094` in its own `.env`.
This host's firewall is default-deny-incoming with only `tailscale0`
allowed — container→host traffic arrives over the Docker bridge interface
(`docker0` or a custom `br-xxxxx`, not `tailscale0`), so it also needs an
explicit rule, e.g.:

```
sudo ufw allow in on docker0 to any port 8094 proto tcp
```

This widens reachability to *any* container on the host, not just Roost's —
an accepted widening of the existing single-user-host threat model, not a
new category of risk.

## Tests

Own small pytest suite:

```
cd host/llm_bridge
source .venv/bin/activate
pip install -r requirements.txt pytest httpx
pytest
```
