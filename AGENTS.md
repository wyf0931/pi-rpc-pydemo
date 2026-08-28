# AGENTS.md

Guidance for AI coding agents (pi, and any other agent) working in this repository.

## What this project is

OMA Studio — an experimental, local-first agent platform. A single FastAPI process serves
a static Alpine.js + DaisyUI frontend and a JSON API, and talks to the
[Pi coding agent](https://github.com/earendil-works/pi) via `pi --mode rpc` (JSONL over
stdin/stdout). TinyDB stores platform metadata only; **Pi owns all message content and
session transcripts**. Status: MVP, single user, localhost.

## Tech stack (and why)

| Layer | Choice | Notes |
| --- | --- | --- |
| Python | 3.11+ managed by **uv** | Never use pip directly; use `uv` / `uv run`. |
| API | FastAPI + Pydantic | Request validation lives in Pydantic models in `app/main.py`. |
| Storage | TinyDB (file `data/platform.json`) | Metadata only. See invariants below. |
| Agent runtime | Pi RPC subprocess | One short-lived Pi process per operation (send / stream / messages). |
| Frontend | Plain static HTML/JS/CSS in `static/` | No bundler. Alpine.js + DaisyUI 5 + Tailwind browser build via CDN. |
| Markdown rendering | marked + DOMPurify + highlight.js + mermaid (CDN) | Sanitized HTML only; never inject raw model output. |
| Typography CSS | Tailwind CLI (`npm run build:css`) | The only frontend build step; output is committed to `static/typography.css`. |

## Commands

```bash
# Setup
cp .env.example .env      # then set PI_CWD to an absolute workspace path
uv sync                   # Python deps (also creates .venv)
pi --version              # Pi CLI must be on PATH, with a provider credential configured

# Run (host)
bin/ops.sh start          # background dev server (uvicorn --reload), logs in .run/uvicorn.log
bin/ops.sh status|restart|stop
# or foreground: uv run uvicorn app.main:app --env-file .env --reload

# Run (Docker — app layer + process layer in one container, state via bind mounts)
docker compose up --build

# Test (run before declaring any work done)
uv run pytest -q

# Frontend CSS (only when changing markdown presentation classes)
npm install
npm run build:css         # frontend/input.css -> static/typography.css (keep it committed)
```

## Repository map

```text
app/
  config.py     Settings dataclass; env vars + a ~20-line built-in .env reader
  store.py      TinyDB wrapper: agents/chats tables, BUILTIN_TOOLS, protected default agent
  pi_rpc.py     PiRpcClient (JSONL bridge) + PiRuntimeManager (process lifecycle, per-chat locks)
  resources.py  Read-only discovery: extensions, skills, MCP servers, provider/model catalog
  files.py      Chat-generated file discovery + authorization (write/edit toolCall provenance)
  main.py       FastAPI app, routes, Pydantic payloads. NOTE: configures itself at import time
static/         index.html, app.js (one Alpine component), styles.css, typography.css (generated)
frontend/       input.css — Tailwind source for static/typography.css
tests/          Mirrors app modules; conftest provides `client` and `temporary_agent` fixtures
bin/ops.sh      Process management (start/stop/restart/status)
Dockerfile      Single image: app layer (Python/FastAPI) + process layer (pi, rg, fd, git)
docker-compose.yml  One-command run; bind mounts for data, workspace, and Pi home
schemas/        Vendored compose-spec JSON schema for offline YAML validation
docs/           Design spec (docs/superpowers/specs/) + README screenshots
data/           Gitignored runtime data: platform.json, pi-sessions/
```

## Architecture invariants (do not break)

1. **Pi is the source of truth for messages.** Never store message bodies, tool results,
   or transcripts in TinyDB. Chats carry metadata only (`id`, `session_id`, `agent_id`,
   `title`, `status`, timestamps). A unit test (`test_chat_index_does_not_store_messages`)
   enforces this.
2. **Chat id == Pi session id.** The UUID is shared deliberately; there is no mapping layer.
   Do not introduce one.
3. **One Agent per chat.** The binding is fixed at the first prompt and never changes.
4. **Discovery ≠ enablement.** `resources.py` only *lists* what exists. An Agent must opt
   in to tools/extensions/skills/MCP servers, and every selection must be validated against
   the discovered catalog before persistence (see create/update handlers in `main.py`).
5. **File serving is authorized twice over.** `resolve_chat_file` only returns files that
   (a) appear in that chat's own `write`/`edit` tool calls and (b) resolve inside
   `PI_CWD`. Both checks are the security model for file view/download — preserve them.
6. **`PI_CWD` is a working directory, not a sandbox.** The MVP has no auth and must not be
   exposed beyond localhost. Don't add "hardening" that implies a security boundary where
   none exists (e.g. path "jails" outside the authorized-files flow).
7. **Single process, single static frontend.** FastAPI serves the API and `static/`; the
   catch-all route returns `index.html`. Don't add a second server or a JS build system
   without an explicit decision.

## Development philosophy

- **Don't reinvent wheels.** Prefer standard-library and community packages over
  hand-rolled code: Pydantic for validation, TinyDB for storage, Alpine.js + DaisyUI for
  UI, marked/DOMPurify/mermaid/highlight.js for rendering. Before writing a utility,
  check whether a small, well-maintained package already covers it.
  *Known deliberate exception:* the mini dotenv reader in `config.py` exists so that
  `uvicorn --reload` workers and tests pick up `.env` without adding a dependency. Don't
  grow it; if env handling becomes more complex, adopt `python-dotenv`/`pydantic-settings`
  instead of extending it.
- **No speculative design.** Build only what a current requirement needs. Future
  capabilities (SandboxRunner, auth, durable datastore, marketplace) live in the README
  Roadmap and the design spec — do not pre-create stubs, interfaces, or config for them.
- **Pragmatism over purity.** Single process, one-file frontend JS, file-based storage,
  plain dicts out of TinyDB (no ORM) are conscious MVP choices, not oversights. Make the
  smallest change that satisfies the requirement; don't add layers (services,
  repositories, DI) until a concrete need appears. When you trade purity for simplicity,
  leave a one-line comment or note it in the design spec.

## Conventions

- **Commits:** conventional style — `feat:`, `fix:`, short imperative subject.
- **Config changes:** adding/renaming an env var means updating `.env.example` *and* the
  README Configuration section in the same change.
- **API changes:** README documents the full HTTP surface table — add/update rows when
  endpoints change.
- **Static assets:** when editing `static/styles.css`, `static/app.js`, or
  `static/typography.css`, bump the `?v=` cache-busting query in `static/index.html`.
- **Errors:** raise `HTTPException` with clear messages; map `PiRpcError` to 503.
- **Style:** modern stdlib typing (`str | None`), dataclasses for settings, no linter is
  configured yet — keep formatting consistent with surrounding code.
- **Never commit:** `data/`, `.env`, `.run/`, `research/`, `.superpowers/`,
  `.playwright-cli/`, `node_modules/`, `.venv/` (all gitignored runtime/scratch).

## Development workflow

The repo has one long-lived branch, `main`, and `origin` (GitHub) is the deployment
remote. Work happens on feature branches; nothing reaches `main` without an explicit
green light from the user.

1. **Branch first.** Never commit feature work directly on `main`. Branch naming:
   `<type>/<short-kebab-name>` — `feat/agent-marketplace`, `fix/file-viewer-scroll`,
   `chore/add-ci`, `docs/agents-md`. The type matches the conventional-commit prefix.
2. **Use a worktree for isolation** when parallel or agent-driven work is involved
   (e.g. pi's managed worktrees, or `git worktree add`): keep the main checkout on
   `main`, do feature work in the worktree's branch. A fresh worktree has no
   `.venv`/`node_modules` (gitignored) — run `uv sync` (and `npm install` if touching
   CSS) before testing there.
3. **Commit small and often** on the feature branch, following the conventional style.
4. **Self-test, then stop — do not merge.** Before reporting completion, `uv run
   pytest -q` must pass in the branch (worktree). Then summarize what changed and how
   it was verified, and **wait for the user's explicit confirmation**. Do not merge,
   do not push to `origin`, even if everything is green.
5. **After user confirmation:** merge the feature branch into `main`
   (`git merge --no-ff <branch>` unless the user asks otherwise), run the test suite
   once more on `main`, then push: `git push origin main`. This push is the deploy step
   for this project — there is no separate pipeline.
6. **`main` stays deployable.** Never push a state that doesn't pass tests, never
   force-push `main`, and never push feature branches to `origin` unless asked.

## Testing

- `uv run pytest -q` must pass before you declare work done.
- `test_store.py`, `test_files.py`, `test_resources.py` are hermetic (use `tmp_path`) —
  keep them that way.
- `test_api.py` boots the real app; because `app.main` configures at import time, API
  tests currently run against the real `data/` directory. Clean up anything you create
  (see the `temporary_agent` fixture pattern).
- Bug fixes get a regression test in the file mirroring the changed module.
- The design spec (`docs/superpowers/specs/2026-08-26-pi-agent-platform-mvp-design.md`)
  documents the RPC event contract and JSONL framing rules — read it before touching
  `pi_rpc.py`.

## Gotchas

- Importing `app.main` has side effects: loads settings, creates `data/` dirs, opens
  TinyDB, ensures the default agent. Don't add more import-time work, and don't import
  `app.main` from scripts casually.
- `@app.on_event("shutdown")` is a deprecated FastAPI API. Don't build on it; if you must
  touch app lifecycle, prefer a lifespan handler — but don't refactor it speculatively.
- Pi RPC processes are short-lived: `send`, `stream`, and `messages` each start one Pi
  process and close it. Don't assume a persistent process; per-chat `asyncio.Lock`s
  serialize prompts and a second concurrent prompt fails with "Chat is busy".
- When `pi-mcp-adapter` is enabled, `pi_rpc.py` writes a temporary MCP config that
  disables all non-selected servers and passes `--mcp-config`; it is deleted via
  `cleanup_paths` on process close.
- Some CDN deps are intentionally unpinned majors (daisyui@5, Tailwind browser@4,
  mermaid@11); changing this is a project decision, not a drive-by fix.
