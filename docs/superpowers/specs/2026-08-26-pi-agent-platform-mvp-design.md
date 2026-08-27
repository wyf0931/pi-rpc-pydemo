# Pi Agent Platform MVP Design

## Goal

Validate the feasibility of a custom agent platform built around Pi RPC mode, Python FastAPI, uv dependency management, TinyDB, and a separated static web UI using DaisyUI and Alpine.js.

The MVP supports direct chat with Pi, persistent Pi-backed chat sessions, agent creation and management, chat history, and a small amount of tool-event visibility.

## Product boundaries

- Chat is the primary entry point.
- Every chat is permanently bound to one Agent. Agent switching is not supported after the first message.
- The Chat page always has a left chat-history sidebar.
- The top navigation switches between Chat and Agents pages.
- The Agents page manages agent definitions only; it is not a chat entry point.
- The default installation creates one protected Agent named `assistant`.
- Agent extensions, skills, tools, and MCP servers are represented as reserved fields and displayed as unconfigured sections, but are not configured through the MVP UI.
- Pi owns all message content and session history. TinyDB stores platform indexes and metadata only.

## Architecture

```text
Browser: static HTML + DaisyUI + Alpine.js
             │ REST/JSON
             ▼
FastAPI API layer
  ├─ AgentRepository / TinyDB
  ├─ ChatRepository / TinyDB
  ├─ PiRuntimeManager
  │    └─ one Pi RPC subprocess per active chat
  └─ PiRpcClient
       └─ strict JSONL stdin/stdout reader
             │
             ▼
      pi --mode rpc
      Pi session directory
```

The API serves the static frontend and JSON endpoints from one FastAPI process. This keeps the frontend/backend contract separated while avoiding a second frontend build system in the MVP.

## Pi session ownership and persistence

Pi is the source of truth for messages, tool results, session IDs, session names, and session files. The platform uses one fixed internal working directory and one fixed Pi `--session-dir` for all platform chats.

TinyDB stores only:

```text
agents: id, name, instruction, model, extensions, skills, tools, mcp_servers,
        created_at, updated_at
chats:  id, session_id, agent_id, title, status, created_at, updated_at,
        last_activity_at
```

`session_file` is intentionally not stored. When a history item is opened, the runtime starts Pi with the same session directory and `--session <session_id>`, then calls `get_state` and `get_messages`.

The chat title is generated from the first user message by a deterministic local function: normalize whitespace, remove line breaks, and truncate to a readable length. The title is sent to Pi using `set_session_name`; the returned `sessionName` is stored as the TinyDB display snapshot.

## Chat lifecycle

1. `POST /api/chats` creates a platform chat with a selected `agent_id` and starts a Pi RPC process.
2. The platform sends `get_state` and records the returned `sessionId`.
3. Before the first prompt, the Chat page shows an Agent select and message composer.
4. The first prompt permanently binds the chat to the selected Agent, generates a title, and sends `set_session_name` followed by `prompt`.
5. After the first prompt, the Agent select becomes a read-only label.
6. `message_update` text deltas are accumulated in memory for the HTTP response. `turn_end`/`agent_end` marks the turn complete.
7. `get_messages` is used when opening a historical chat. No message body is copied into TinyDB.
8. `abort` is available while a prompt is running.

Status mapping:

```text
created  → chat exists with no user prompt
starting → Pi process is being launched
ready    → Pi is available and isStreaming=false
running  → agent_start, turn_start, or isStreaming=true
error    → RPC failure, timeout, invalid protocol, or unexpected exit
stopped  → explicit abort or application shutdown
```

The runtime manager serializes prompts per chat. A second prompt while running returns a conflict response rather than attempting unsupported concurrent RPC work.

## API contract

```text
GET    /api/health

GET    /api/agents
POST   /api/agents
GET    /api/agents/{agent_id}
PATCH  /api/agents/{agent_id}
DELETE /api/agents/{agent_id}

GET    /api/chats
POST   /api/chats
GET    /api/chats/{chat_id}
GET    /api/chats/{chat_id}/messages
POST   /api/chats/{chat_id}/messages
POST   /api/chats/{chat_id}/abort
```

`POST /api/chats/{chat_id}/messages` returns the completed turn in the MVP. The internal Pi event stream is designed so the endpoint can later be upgraded to SSE or WebSocket streaming without changing the Pi adapter.

## RPC event handling

The JSONL adapter must split only on LF, accept CRLF by stripping a trailing CR, and keep stderr separate from stdout. It handles:

- `response`: command acceptance or failure
- `message_update`: assistant text deltas and tool-call deltas
- `tool_execution_start`, `tool_execution_update`, `tool_execution_end`: optional live event summaries
- `agent_start`, `agent_end`, `turn_start`, `turn_end`: lifecycle state transitions
- `session_start`: session identity and startup information
- `extension_ui_request`: explicitly unsupported in the MVP, with a bounded error path

Tool events may be returned in the current message response as transient metadata, but are never persisted separately in TinyDB.

## Markdown message rendering

Assistant text is expected to be Markdown. The frontend renders assistant messages with a Markdown parser and sanitizes the generated HTML before inserting it into the DOM. Raw assistant text remains available for copy and is never replaced as the stored source.

Rendering requirements:

- headings, emphasis, lists, links, blockquotes, tables, and horizontal rules
- fenced code blocks with language labels where present
- inline code and multiline code readability
- copy-code action for fenced code blocks
- safe link handling (`https` and standard safe protocols)
- sanitized HTML; model-provided scripts, event attributes, and unsafe URLs are removed
- user messages remain escaped plain text unless explicitly marked otherwise
- loading state can show the accumulated text as plain text until the final Markdown render

The MVP can use browser-delivered `marked` plus `DOMPurify` from pinned CDN URLs, or equivalent vendored static assets if offline operation is required. Markdown rendering is isolated behind a small Alpine helper so the renderer can later be replaced without changing API responses.

## UI design

The visual direction is a calm developer workbench: graphite background, warm light content panels, acid-green active states, amber tool states, restrained borders, and compact status badges. Chat content is the visual center rather than large message bubbles.

Global shell:

- topbar with Pi mark, platform name, `Chat`, and `Agents`
- persistent left history sidebar with `New chat`, Today/Earlier grouping, title, Agent name, status, and timestamp
- responsive mobile drawer for history

Chat page:

- empty state with Agent select, message input, and Send action
- active conversation header showing title, bound Agent, and status
- assistant Markdown messages, user messages, and optional collapsed tool summaries
- disabled composer with Abort while running
- recoverable inline error with retry action
- right-side Agent card list in the empty/new-chat context, with `New agent` inside that list

Agents page:

- card grid showing name, instruction summary, model, chat count, and status
- `New agent` action in the card list area
- card click opens a detail dialog
- protected default `assistant` cannot be deleted

Agent detail dialog groups fields into:

- Basics: name, instruction, model, created time
- Extensions: extensions, skills, tools, MCP servers, each shown as unconfigured/reserved

## Error handling

Return clear HTTP errors for missing Agent/Chat, busy Chat, invalid input, unavailable Pi executable, missing provider credentials, RPC startup failure, prompt rejection, timeout, and unexpected process exit. Preserve the Chat metadata and historical Pi session when a turn fails.

FastAPI startup and shutdown must reclaim all child processes. Each RPC process has a bounded command/turn timeout and a stderr capture path suitable for development logs.

## Verification plan

- Unit test TinyDB repositories, default-agent bootstrap, title generation, and status mapping.
- Unit test JSONL framing with LF, CRLF, partial chunks, and malformed lines.
- Test RPC adapter command correlation and event collection with a fake Pi process.
- API test Agent CRUD, Chat creation, Agent binding, history lookup, busy conflict, abort, and failure responses.
- Browser smoke test: load Chat, create a chat, choose assistant, send a message, render Markdown, open history, switch to Agents, create an Agent, open its detail dialog, and verify reserved extension sections.
- Manual integration test against the local Pi CLI with configured provider credentials and at least one tool-enabled prompt.

## MVP acceptance criteria

- A fresh install shows the protected `assistant` Agent.
- A user can create an Agent with name and instruction.
- A user can start a Chat by selecting an Agent and sending a message.
- The selected Agent cannot be changed after the first message.
- Pi responses are shown in the UI with Markdown rendering.
- Tool lifecycle events do not corrupt the response and can be viewed as summaries when present.
- Chat history remains visible in the sidebar after reload.
- Clicking a historical Chat restores its messages from Pi using only the stored session ID.
- Agent cards and detail dialog work, including reserved extension sections.
- Application shutdown does not leave Pi child processes running.
