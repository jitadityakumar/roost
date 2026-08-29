"""Entrypoint: `python -m llm_bridge`. Run from host/llm_bridge/ with its own
venv (see README.md) -- never from inside the Roost container."""
import uvicorn

from llm_bridge.app import app
from llm_bridge.config import PORT

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
