# OMA Studio

An experimental, local-first agent platform built with **FastAPI**, **Pi RPC mode**, and a lightweight **Alpine.js + DaisyUI** web interface.

OMA Studio explores a practical separation of concerns:

- Pi owns agent execution, tool calls, streaming events, and durable session transcripts.
- The platform owns agents, chat metadata, resource discovery, and the web experience.
- TinyDB stores only platform metadata; it does not duplicate Pi message history.

> Status: MVP / active experiment. APIs, storage, and sandboxing integrations may change.

## Screenshots

### New chat

![OMA Studio new chat page](docs/images/chat-page.png)

Start a new Pi session by selecting an Agent once, then send the first message. An Agent is bound to the chat for its lifetime, so a conversation cannot silently switch instructions, tools, or models halfway through.

### Agent library

![OMA Studio agents page](docs/images/agents-page.png)

Agents are reusable definitions. The card list is intentionally separate from the chat entry point: create or edit a definition first, then select it when starting a new chat.

## Features

- Chat with Pi through RPC mode, including streamed assistant output.
- Pi-managed session history, addressable at `/chat/<chat-id>`.
- Markdown rendering for assistant messages, code blocks, tables, lists, thinking, tool calls, and collapsible tool results.
- Generated-file drawer for Chat sessions, with metadata cards and a new-tab Markdown viewer with Mermaid support.
- Library page aggregating Agent-created files with Agent filtering, name search, pagination, download, and source-chat links.
- Agent definitions with instruction, Provider, Model, built-in tool allowlist, extensions, skills, and MCP servers.
- Read-only discovery of Pi resources from the configured Pi home directory.
- Light and Dark themes with a DaisyUI `swap swap-rotate` control.
- A small operational CLI: `bin/ops.sh start|stop|restart|status|logs` (Docker Compose mode).

## Design principles

- **Pi is the source of truth for messages.** The platform does not copy message transcripts into TinyDB.
- **One Agent per chat.** An Agent's instruction, Provider, Model, tool allowlist, extensions, skills, and MCP selection are fixed when a chat starts.
- **Explicit capability selection.** Discovering a resource does not enable it. Agents must opt in to tools, extensions, skills, and MCP servers.
- **Local-first, sandbox-ready.** The MVP runs locally for fast iteration, while its execution boundary is designed to move behind a future `SandboxRunner`.

## Architecture

```text
Browser (Alpine.js + DaisyUI)
        │ HTTP / SSE
        ▼
FastAPI
  ├── TinyDB: agents + chat metadata
  ├── Pi resource discovery
  └── Pi RPC bridge
          │ JSONL RPC
          ▼
      Pi coding agent
  ├── Pi session JSONL history
  ├── tools / extensions / skills
  └── MCP adapter (optional)
```

### Request flow

```text
New chat
  → TinyDB creates a chat record using the chat UUID as Pi session ID
  → first user message starts Pi RPC with that Agent configuration
  → FastAPI proxies JSONL events as SSE to the browser
  → Pi persists the transcript in its session directory

Open history
  → FastAPI starts a short Pi RPC process with --session <chat-id>
  → asks Pi for get_messages
  → renders the Pi-managed transcript
```

The session UUID is deliberately shared between platform metadata and Pi. This avoids a mapping layer and keeps Pi session files authoritative.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A local [Pi coding agent](https://github.com/earendil-works/pi)
- A configured Pi provider credential, such as DeepSeek

## Quick start

```bash
cp .env.example .env
bin/ops.sh start
```

`ops.sh` runs the platform in Docker Compose (app layer + process layer in one
container, storage on host mounts — see [Docker](#docker)); no `uv sync` required for
this path.

Open <http://127.0.0.1:8000>.

### Docker

Run the whole platform in one lightweight container — the app layer (FastAPI + web UI)
and the process layer (Pi CLI, ripgrep, fd, git) share a single image; all state stays
on the host through bind mounts:

```bash
docker compose up --build
```

| Mount | Container path | Purpose |
| --- | --- | --- |
| `./data` | `/app/data` | Platform metadata + Pi session transcripts |
| `${PI_CWD:-/workspace}` host mount of `~/.oma-studio/workspace` | `/workspace` | Agent working directory |
| `~/.pi/agent` | `/home/node/.pi/agent` | Extensions, skills, MCP config, model catalog, provider auth |

Compose reads `.env` for `PI_PROVIDER`, `PI_MODEL`, the resource defaults, and the
workspace path; container-internal paths are fixed in `docker-compose.yml` and always
override `.env` values. No reverse proxy or extra services — FastAPI serves the API and
UI directly, and `init: true` reaps the short-lived Pi subprocesses the app spawns. When the
host reaches model providers through a VPN/proxy, set `OMA_PROXY` (e.g. with
Colima: `http://192.168.5.2:7897`) and the container pins its outbound model
calls to it via Node 24 proxy support.

Notes:

- Mounting `~/.pi/agent` exposes provider credentials and executable extensions to the
  container. Only mount a Pi home you trust.
- The container is a process boundary, not a security sandbox: the `PI_CWD` caveats from
  [Security and sandboxing](#security-and-sandboxing) apply unchanged.
- On Linux hosts where bind-mount ownership matters, add `user: "1000:1000"` (or your
  UID) to the service in `docker-compose.yml`.

Use the operational helper after the initial setup:

```bash
bin/ops.sh status
bin/ops.sh restart
```

Run the test suite:

```bash
uv run pytest -q
```

## Configuration

Create `.env` from the example and adjust paths for your machine:

```dotenv
PI_CLI_PATH=pi
PI_PLATFORM_DATA_DIR=/absolute/path/to/.oma-studio/data
PI_SESSION_DIR=/absolute/path/to/.oma-studio/data/pi-sessions
PI_CWD=/absolute/path/to/.oma-studio/workspace
PI_HOME=~/.pi/agent
PI_PROVIDER=deepseek
PI_MODE=production
JINA_API_KEY=
BAIDU_SEARCH_API_KEY=
BAIDU_SEARCH_BASE_URL=https://api.qnaigc.com/v1
```

`PI_CWD` is Pi's working directory. It is **not** a filesystem security boundary: Pi can access anything available to the operating-system user when tools such as `bash` are enabled.

### Providers and models

Provider, model, and supported thinking levels are discovered from `~/.pi/agent/models.json`. An Agent can override the global `PI_PROVIDER`, `PI_MODEL`, and `PI_THINKING_LEVEL` defaults. The platform validates that the selected model belongs to the selected provider before starting Pi. Pi starts with `--thinking <level>`; the default level is `low`.

The Agent dialog presents a Provider select and a filtered Model select. Only names are shown in the UI; the stable Provider and Model IDs are retained in Agent metadata and passed to Pi as `--provider` and `--model`.

`PI_MODE=production` applies the quiet conversation view, retaining only `read`, `write`, `edit`, and collapsed `Thinking` calls. For temporary diagnostics, append `?mode=development` to a chat URL; the URL value takes precedence over the environment setting.

### Extensions, skills, and MCP

The Agent form discovers resources without executing them:

- Extensions from `~/.pi/agent/extensions` and managed Pi npm packages.
- Skills from `~/.pi/agent/skills`.
- MCP servers from standard `mcp.json` locations and the project `.mcp.json`.

Enable only resources you trust. Extensions and MCP servers execute code or connect to external systems.

### Built-in tools

An Agent selects an allowlist from Pi's built-in tools:

| Tool | Purpose |
| --- | --- |
| `read` | Read a file |
| `write` | Create or overwrite a file |
| `edit` | Apply exact text replacements |
| `bash` | Run a shell command |
| `grep` | Search file contents |
| `find` | Find files |
| `ls` | List a directory |

OMA Studio also provides two platform tools through `extensions/oma-web-tools.ts`:

| Tool | Purpose |
| --- | --- |
| `web_fetch` | Fetch a URL as readable Markdown through Jina Reader |
| `web_search` | Search the web through the Qiniu Baidu Search API |

Set `JINA_API_KEY` and `BAIDU_SEARCH_API_KEY` in `.env` when enabling the corresponding tools. In development mode, their tool calls and results are retained in the chat transcript; production mode keeps the quieter process view.

If the `pi-mcp-adapter` extension is selected, its `mcp` and `mcpScript` tools are added to the Pi allowlist so enabled MCP servers can be called.

## Data ownership

| Data | Owner | Default location |
| --- | --- | --- |
| Agent definitions and chat metadata | OMA Studio / TinyDB | `~/.oma-studio/data/platform.json` |
| Pi session transcripts | Pi | `~/.oma-studio/data/pi-sessions` |
| Agent working directory | Pi / platform | `~/.oma-studio/workspace` |
| Pi configuration, extensions, skills, models | Pi | `~/.pi/agent` |

TinyDB records chat identity, title, Agent binding, timestamps, and status only. It is intentionally not a second message store.

## HTTP surface

This MVP is a single FastAPI application with a static frontend. The main endpoints are:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Runtime health and active Pi process count |
| `GET /api/agents` | List Agent definitions |
| `POST /api/agents` | Create an Agent definition |
| `PATCH /api/agents/{id}` | Update an Agent definition |
| `DELETE /api/agents/{id}` | Delete a non-default Agent |
| `GET /api/resources` | Discover extensions, skills, MCP servers, Providers, and Models |
| `GET /api/chats` | List chat metadata |
| `POST /api/chats` | Create a chat record and external Pi session ID |
| `GET /api/chats/{id}/messages` | Read history from Pi |
| `POST /api/chats/{id}/messages` | Stream a Pi response as server-sent events |
| `GET /api/chats/{id}/files` | List files written or edited by that Chat |
| `GET /api/chats/{id}/files/content` | Read an authorized Chat-generated text file |
| `GET /api/chats/{id}/files/download` | Download an authorized Chat-generated file |
| `GET /api/library/files` | Search and paginate files created by Agents |
| `GET /api/autopilots` | List and filter scheduled Agent instructions |
| `POST /api/autopilots` | Create a scheduled Agent instruction |
| `PATCH /api/autopilots/{id}` | Edit or enable/disable an Autopilot |
| `DELETE /api/autopilots/{id}` | Delete an Autopilot definition |
| `POST /api/autopilots/{id}/run` | Queue a manual run |
| `GET /api/autopilots/{id}/runs` | List execution records and linked Chat sessions |

## Security and sandboxing

Pi does not provide a built-in filesystem or process sandbox. This MVP should be run only with trusted agents, extensions, MCP servers, and workspaces.

In particular:

- `PI_CWD` is a default working directory, not an access-control boundary.
- `bash` can access the same files and processes as the OS user running Pi.
- A host `~/.pi/agent` directory may contain provider credentials and executable extensions.
- Do not expose this development server directly to the internet.

The planned production execution model is a pluggable `SandboxRunner`, beginning with an OpenShell integration. The goal is one policy-controlled sandbox per active chat or project, with explicit workspace, network, credential, CPU, and memory limits.

See [OpenShell sandbox runner proposal](https://github.com/wyf0931/pi-rpc-pydemo/issues/1) for the intended integration and acceptance criteria.

## Development

Local development server with hot reload (no Docker):

```bash
uv run uvicorn app.main:app --env-file .env --reload
```

The page is plain static HTML, JavaScript, and CSS under `static/`; FastAPI serves it together with the API. The interactive MVP still runs without a frontend build step, while the file viewer's typography stylesheet is generated with Tailwind CLI:

```bash
npm install
npm run build:css
```

The build uses the official `@tailwindcss/typography` plugin. Keep `static/typography.css` in sync when changing Markdown presentation classes.

Useful commands:

```bash
bin/ops.sh start
bin/ops.sh status
bin/ops.sh restart
bin/ops.sh stop
bin/ops.sh logs
```

### Verification

```bash
uv run pytest -q
```

The test suite covers TinyDB persistence, Agent Provider/Model overrides, model catalog discovery, and basic API behavior. Browser screenshots in this README are captured with Playwright at 1600×1000.

### Troubleshooting

| Symptom | Check |
| --- | --- |
| Pi process cannot start | Confirm `PI_CLI_PATH`, then run `pi --version` in the same shell. |
| No models in Agent dialog | Confirm `PI_HOME/models.json` is valid JSON with a `providers` object. |
| Provider request fails | Confirm the Provider credential is configured for Pi and the selected Model belongs to that Provider. |
| MCP tool is unavailable | Select `pi-mcp-adapter`, enable the intended MCP server, and allow the associated tool capability. |
| History is empty | Confirm the Pi session directory is retained and the chat session ID has not been removed. |

## Roadmap

- [ ] OpenShell-backed `SandboxRunner` for policy-controlled Pi execution.
- [ ] Project workspaces and per-project sandbox policies.
- [ ] Durable production datastore and user authentication.
- [ ] Agent marketplace, autopilots, and library modules.

## Contributing

Issues and pull requests are welcome. Please include reproduction steps for bugs and add or update tests for behavioral changes.

## License

Copyright (c) 2026 wyf0931

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

- You are free to use, study, modify, and redistribute this project, including for internal business use.
- If you distribute the software, or run a modified version as a network service, you must release the modified source code under AGPL-3.0 as well.
- Any use outside AGPL-3.0 terms — for example, embedding this project or a derivative into a closed-source product — requires the author's explicit prior written agreement. Contact the repository owner to arrange it.

Contributions are accepted under AGPL-3.0.
