# OMA Studio — one lightweight image, two system layers:
#   app layer     : Python 3.11 + FastAPI + static UI (this repo)
#   process layer : Pi coding agent (Node) + curl / jq / ripgrep / fd / git
# State (platform data, sessions, workspace, Pi home) stays on the host
# through bind mounts — nothing is baked into the image.

FROM node:24.20.0-bookworm-slim

# Process-layer tools. fd ships as fd-find on Debian. curl and jq are useful
# for ordinary HTTP/API debugging from the Agent's bash tool; structured web
# research should still prefer the platform web_fetch/web_search tools.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       bash ca-certificates curl git jq ripgrep fd-find python3 python3-venv \
  && ln -s /usr/bin/fdfind /usr/local/bin/fd \
  && rm -rf /var/lib/apt/lists/*

# uv for reproducible installs from uv.lock (no pip in the image)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Pi CLI — the app layer spawns it via PI_CLI_PATH (multi-process: one
# short-lived pi process per chat operation)
RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.84.4

WORKDIR /app

# Dependencies first for layer caching
COPY pyproject.toml uv.lock ./
# Optional proxy for the dependency-install step only (e.g. a host-side VPN
# when PyPI direct routes are slow from build containers). Empty by default,
# so CI and normal builds stay direct.
ARG UV_PROXY=""
RUN UV_PYTHON=/usr/bin/python3 sh -c '[ -z "$UV_PROXY" ] || export HTTPS_PROXY="$UV_PROXY" HTTP_PROXY="$UV_PROXY"; exec uv sync --frozen --no-dev'

COPY app ./app
COPY extensions ./extensions
COPY static ./static

# Non-root: keeps bind-mounted file ownership predictable
USER node
ENV HOME=/home/node \
    PI_CLI_PATH=pi \
    PI_HOME=/home/node/.pi/agent \
    PI_PLATFORM_DATA_DIR=/app/data \
    PI_SESSION_DIR=/app/data/pi-sessions \
    PI_LOG_DIR=/app/logs \
    PI_CWD=/workspace

EXPOSE 8000
# Single worker on purpose: runtime state (Pi processes, per-chat locks)
# lives in this process; concurrency comes from multiple pi subprocesses.
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
