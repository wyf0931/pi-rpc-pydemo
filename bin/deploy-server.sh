#!/usr/bin/env bash
# OMA Studio production deploy — server side. Invoked by GitHub Actions
# (.github/workflows/ci.yml, deploy job syncs this file to
# /opt/apps/oma-studio/bin/deploy.sh and runs it), or by hand:
#   bin/deploy-server.sh [ref]     ref = branch name (default main) or a
#                                  full 40-char commit SHA.
#
# Server layout (provisioned once, outside this script):
#   /opt/apps/oma-studio/.env.ops                        stable env + secrets
#   /opt/apps/oma-studio/releases/<UTCts>-<sha>/         git clone of this repo
#   /opt/apps/oma-studio/current -> releases/<latest healthy release>
#   /opt/apps/oma-studio/shared/                         oma/{data,workspace}, pi-home/agent
set -euo pipefail

ROOT=/opt/apps/oma-studio
REPO_URL="https://github.com/wyf0931/pi-rpc-pydemo.git"
REF="${1:-main}"

# Load OMA_PORT etc. for the health check.
set -a
. "$ROOT/.env.ops"
set +a
PORT="${OMA_PORT:-8000}"

# Pin an exact commit when the caller passes a full SHA (CI path); fall back
# to branch-head resolution for manual runs.
if [[ "$REF" =~ ^[0-9a-f]{40}$ ]]; then
  SHA="${REF:0:7}"
  clone_args=(-q "$REPO_URL")
  checkout="$REF"
else
  SHA="$(git ls-remote "$REPO_URL" "refs/heads/$REF" | cut -c1-7)"
  [ -n "$SHA" ] || {
    echo "cannot resolve branch '$REF' on $REPO_URL" >&2
    exit 1
  }
  clone_args=(-q -b "$REF" "$REPO_URL")
  checkout=""
fi

REL="$ROOT/releases/$(date -u +%Y%m%d%H%M%S)-$SHA"
if [ -e "$REL" ]; then
  echo "release dir already exists: $REL — re-deploying same sha, re-cloning"
  rm -rf "$REL"
fi

echo "==> cloning $REPO_URL (${checkout:-branch $REF}, $SHA) into $REL"
git clone "${clone_args[@]}" "$REL"
[ -z "$checkout" ] || git -C "$REL" checkout -q --detach "$checkout"
ln -s ../../.env.ops "$REL/.env"

cd "$REL"
LOG_DIR="${PI_LOG_DIR:-./logs}"
if [[ "$LOG_DIR" != /* ]]; then
  LOG_DIR="$REL/$LOG_DIR"
fi
mkdir -p "$LOG_DIR"
if ! chown 1000:1000 "$LOG_DIR" 2>/dev/null; then
  chmod 0777 "$LOG_DIR"
fi
echo "==> building image and restarting service (project: ${COMPOSE_PROJECT_NAME:-oma-studio})"
docker compose -f docker-compose.yml -f deploy/docker-compose.production.yaml up -d --build

echo "==> waiting for health on 127.0.0.1:$PORT"
ok=0
for _ in $(seq 1 45); do
  if curl -sf --max-time 3 "http://127.0.0.1:${PORT}/api/health" >/dev/null; then
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" -ne 1 ]; then
  echo "health check FAILED; keeping release for debugging: $REL" >&2
  docker compose logs --tail 50 oma-studio >&2 || true
  exit 1
fi

ln -sfn "$REL" "$ROOT/current"
echo "==> current -> $REL"

# Keep the 3 most recent releases.
ls -1d "$ROOT"/releases/* 2>/dev/null | sort | head -n -3 | while read -r old; do
  echo "==> pruning old release $old"
  rm -rf "$old"
done

echo "==> deploy complete: $REL"
