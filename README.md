# OMA Studio

An experimental, local-first agent platform built with **FastAPI**, **Pi RPC mode**, and a lightweight **Alpine.js + DaisyUI** web interface.

OMA Studio explores a practical separation of concerns:

- Pi owns agent execution, tool calls, streaming events, and durable session transcripts.
- The platform owns agents, chat metadata, resource discovery, and the web experience.
- TinyDB stores only platform metadata; it does not duplicate Pi message history.

> Status: MVP / active experiment. APIs, storage, and sandboxing integrations may change.

## Features

- Chat with Pi through RPC mode, including streamed assistant output.
- Pi-managed session history, addressable at `/chat/<chat-id>`.
- Markdown rendering for assistant messages, code blocks, tables, lists, thinking, tool calls, and collapsible tool results.
- Agent definitions with instruction, Provider, Model, built-in tool allowlist, extensions, skills, and MCP servers.
- Read-only discovery of Pi resources from the configured Pi home directory.
- Multiple DaisyUI-compatible themes: Light, Cupcake, Lemonade, and Dark.
- A small operational CLI: `bin/ops.sh start|stop|restart|status`.

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

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A local [Pi coding agent](https://github.com/earendil-works/pi)
- A configured Pi provider credential, such as DeepSeek

## Quick start

```bash
cp .env.example .env
uv sync
bin/ops.sh start
```

Open <http://127.0.0.1:8000>.

Run the test suite:

```bash
uv run pytest -q
```

## Configuration

Create `.env` from the example and adjust paths for your machine:

```dotenv
PI_CLI_PATH=pi
PI_PLATFORM_DATA_DIR=data
PI_SESSION_DIR=data/pi-sessions
PI_CWD=/absolute/path/to/a-safe-workspace
PI_HOME=~/.pi/agent
PI_PROVIDER=deepseek
```

`PI_CWD` is Pi's working directory. It is **not** a filesystem security boundary: Pi can access anything available to the operating-system user when tools such as `bash` are enabled.

### Providers and models

Provider and model options are discovered from `~/.pi/agent/models.json`. An Agent can override the global `PI_PROVIDER` and `PI_MODEL` defaults. The platform validates that the selected model belongs to the selected provider before starting Pi.

### Extensions, skills, and MCP

The Agent form discovers resources without executing them:

- Extensions from `~/.pi/agent/extensions` and managed Pi npm packages.
- Skills from `~/.pi/agent/skills`.
- MCP servers from standard `mcp.json` locations and the project `.mcp.json`.

Enable only resources you trust. Extensions and MCP servers execute code or connect to external systems.

## Data ownership

| Data | Owner | Default location |
| --- | --- | --- |
| Agent definitions and chat metadata | OMA Studio / TinyDB | `data/platform.json` |
| Pi session transcripts | Pi | `data/pi-sessions` |
| Pi configuration, extensions, skills, models | Pi | `~/.pi/agent` |

## Security and sandboxing

Pi does not provide a built-in filesystem or process sandbox. This MVP should be run only with trusted agents, extensions, MCP servers, and workspaces.

The planned production execution model is a pluggable `SandboxRunner`, beginning with an OpenShell integration. The goal is one policy-controlled sandbox per active chat or project, with explicit workspace, network, credential, CPU, and memory limits.

## Development

```bash
uv run uvicorn app.main:app --env-file .env --reload
```

Useful commands:

```bash
bin/ops.sh start
bin/ops.sh status
bin/ops.sh restart
bin/ops.sh stop
```

## Roadmap

- [ ] OpenShell-backed `SandboxRunner` for policy-controlled Pi execution.
- [ ] Project workspaces and per-project sandbox policies.
- [ ] Durable production datastore and user authentication.
- [ ] Agent marketplace, autopilots, and library modules.

## Contributing

Issues and pull requests are welcome. Please include reproduction steps for bugs and add or update tests for behavioral changes.

## License

No license has been selected yet. Do not treat this repository as reusable open-source software until a license is added.
