# Private deployment templates

Copy `env.production.example` to `/opt/apps/oma-studio/.env.ops`, replace the
two passwords, and create the configured host directories. Keep state outside
release directories so an upgrade or rollback never replaces metadata, Pi
sessions, workspace files, logs, or provider credentials.

Set `PI_HOST_AGENTS_HOME` to the host directory containing shared,
agent-neutral skills. Compose mounts it at `/home/node/.agents`, independently
from `PI_HOST_HOME`; do not replace this mount with a symlink.

The deployment script requires this directory to exist before it recreates the
container, so a missing mount cannot silently hide the community skill catalog.
The directory is mounted independently; existing skills in `PI_HOST_HOME` are
not moved automatically.

Deploy with the root Compose definition plus this production overlay. The
example binds FastAPI to loopback for a separately managed TLS reverse proxy.
It does not add a proxy or represent `PI_CWD` as a sandbox.

```bash
docker compose --env-file /opt/apps/oma-studio/.env.ops \
  -f docker-compose.yml -f deploy/docker-compose.production.yaml config -q
```
