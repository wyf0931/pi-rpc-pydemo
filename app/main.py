import asyncio
import copy
import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .api.routers.autopilots import (
    create_executor as create_autopilot_executor,
)
from .api.routers.autopilots import (
    create_router as create_autopilot_router,
)
from .api.routers.identity import create_router as create_identity_router
from .api.routers.marketplace import create_router as create_marketplace_router
from .api.routers.resource_catalog import (
    catalog_response,
)
from .api.routers.resource_catalog import (
    create_router as create_resource_catalog_router,
)
from .api.routers.shares import create_router as create_share_router
from .autopilots import AutopilotScheduler
from .avatars import (
    avatar_file,
    copy_avatar,
    remove_avatar,
    save_avatar,
)
from .core.application import create_app, create_context
from .files import (
    delete_chat_files,
    discover_chat_files,
    discover_session_files,
    read_session_messages,
    resolve_chat_file,
)
from .pi_rpc import ActiveTurn, PiRpcError
from .resources import discover_resources
from .store import (
    SUPPORTED_TOOLS,
    now_iso,
    pi_terminal_failure,
)

context = create_context()
settings = context.settings
store = context.store
runtime = context.runtime

# SSE heartbeat cadence. Any proxy/browser idle timeout must be far larger
# than this (Cloudflare cuts idle streams at ~100s).
SSE_KEEPALIVE_SECONDS = 20.0
app = create_app(context)
logger = logging.getLogger(__name__)
SESSION_COOKIE = "oma_session"


def _request_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    return store.get_session_user(token) if token else None


def _is_auth_exempt(path: str) -> bool:
    return (
        path in {"/api/health", "/api/auth/login", "/api/auth/session"}
        or path.startswith("/api/share/")
        or not path.startswith("/api/")
    )


def _require_admin(request: Request) -> dict:
    user = request.state.user
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def _user_id(request: Request) -> str:
    user = request.state.user
    if not user:
        raise HTTPException(401, "Authentication required")
    return user["id"]


def _can_access(record: dict, request: Request) -> bool:
    return record.get("user_id") == _user_id(request)


def _visible_or_404(record: dict | None, request: Request, label: str) -> dict:
    if not record or not _can_access(record, request):
        raise HTTPException(404, f"{label} not found")
    return record


def _visible_records(records: list[dict], request: Request) -> list[dict]:
    user_id = _user_id(request)
    return [record for record in records if record.get("user_id") == user_id]


@app.middleware("http")
async def require_login(request: Request, call_next):
    user = _request_user(request)
    request.state.user = user
    if not user and not _is_auth_exempt(request.url.path):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return await call_next(request)


app.include_router(create_identity_router(settings, store))
app.include_router(create_resource_catalog_router(settings))
app.include_router(
    create_marketplace_router(
        settings, _require_admin, lambda: catalog_response(settings), logger
    )
)
autopilot_executor = create_autopilot_executor(store, runtime)
scheduler = AutopilotScheduler(store, autopilot_executor)
context.scheduler = scheduler
app.include_router(
    create_autopilot_router(
        store, scheduler, _visible_or_404, _visible_records, _user_id
    )
)


def _has_session_file(chat: dict) -> bool:
    session_id = chat.get("session_id") or chat.get("id")
    return any(settings.pi_session_dir.glob(f"*_{session_id}.jsonl"))


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=10000)
    provider: str | None = None
    model: str | None = None
    thinking_level: str | None = None
    tools: list[str] | None = None
    extensions: list[str] | None = None
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    instruction: str | None = Field(default=None, min_length=1, max_length=10000)
    provider: str | None = None
    model: str | None = None
    thinking_level: str | None = None
    tools: list[str] | None = None
    extensions: list[str] | None = None
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None


class AgentPublish(BaseModel):
    version: str = Field(pattern=r"^v?\d+\.\d+\.\d+$")


class AgentInstall(BaseModel):
    version: str | None = Field(default=None, pattern=r"^v?\d+\.\d+\.\d+$")


class ChatCreate(BaseModel):
    agent_id: str


class ChatUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100000)


@app.get("/api/health")
async def health():
    active_processes = sum(
        1
        for client in runtime.clients.values()
        if client.process and client.process.returncode is None
    )
    return {"ok": True, "active_processes": active_processes}


@app.get("/api/agents")
async def list_agents(request: Request):
    return {"agents": _visible_records(store.list_agents(), request)}


@app.post("/api/agents", status_code=201)
async def create_agent(payload: AgentCreate, request: Request):
    owner_id = _user_id(request)
    if any(
        agent["name"].casefold() == payload.name.strip().casefold()
        for agent in _visible_records(store.list_agents(), request)
    ):
        raise HTTPException(409, "Agent name already exists")
    tools = (
        payload.tools if payload.tools is not None else list(settings.pi_default_tools)
    )
    if any(tool not in SUPPORTED_TOOLS for tool in tools):
        raise HTTPException(400, "Unsupported tool")
    catalog = discover_resources(settings.pi_home, settings.pi_cwd)
    allowed_extensions = {item["path"] for item in catalog["extensions"]}
    allowed_skills = {item["path"] for item in catalog["skills"]}
    if any(path not in allowed_extensions for path in payload.extensions or []):
        raise HTTPException(400, "Unsupported extension path")
    if any(path not in allowed_skills for path in payload.skills or []):
        raise HTTPException(400, "Unsupported skill path")
    allowed_servers = {item["id"] for item in catalog["mcp_servers"]}
    if any(name not in allowed_servers for name in payload.mcp_servers or []):
        raise HTTPException(400, "Unsupported MCP server")
    _validate_model_selection(payload.provider, payload.model, catalog)
    _validate_thinking_level(payload.thinking_level)
    return store.create_agent(
        payload.name,
        payload.instruction,
        payload.provider,
        payload.model,
        tools,
        payload.extensions,
        payload.skills,
        payload.mcp_servers or [],
        thinking_level=payload.thinking_level,
        user_id=owner_id,
    )


def _normalize_agent_version(version: str) -> str:
    value = version.strip()
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise HTTPException(422, "Agent version must use SemVer, for example v1.0.0")
    return value if value.startswith("v") else f"v{value}"


def _market_agent_view(publication: dict) -> dict:
    latest = publication["latest"]
    source_agent = store.get_agent(publication["source_agent_id"])
    return {
        "id": publication["id"],
        "name": latest["content"]["name"],
        "instruction": latest["content"]["instruction"],
        "provider": latest["content"].get("provider"),
        "model": latest["content"].get("model"),
        "thinking_level": latest["content"].get("thinking_level"),
        "tools": latest["content"].get("tools", []),
        "extensions": latest["content"].get("extensions", []),
        "skills": latest["content"].get("skills", []),
        "mcp_servers": latest["content"].get("mcp_servers", []),
        "version": latest["version"],
        "content_hash": latest["content_hash"],
        "author": publication["author_username"],
        "install_count": publication.get("install_count", 0),
        "source_agent_id": publication["source_agent_id"],
        "avatar_available": bool(source_agent and source_agent.get("avatar_path")),
    }


@app.get("/api/market/agents")
async def list_market_agents():
    return {
        "agents": [_market_agent_view(item) for item in store.list_agent_publications()]
    }


@app.post("/api/agents/{agent_id}/publish")
async def publish_agent(agent_id: str, payload: AgentPublish, request: Request):
    agent = _visible_or_404(store.get_agent(agent_id), request, "Agent")
    version = _normalize_agent_version(payload.version)
    publication = next(
        (
            item
            for item in store.list_agent_publications()
            if item["source_agent_id"] == agent_id
        ),
        None,
    )
    if publication and store.has_agent_publication_version(publication["id"], version):
        raise HTTPException(409, f"Agent version {version} already exists")
    published = store.publish_agent(agent, _user_id(request), version)
    return {"agent": _market_agent_view(published)}


@app.get("/api/market/agents/{publication_id}/avatar")
async def get_market_agent_avatar(publication_id: str):
    publication = store.get_agent_publication(publication_id)
    if not publication:
        raise HTTPException(404, "Published Agent not found")
    agent = store.get_agent(publication["source_agent_id"])
    path = avatar_file(settings.data_dir, agent) if agent else None
    if not path:
        raise HTTPException(404, "Published Agent avatar not found")
    return FileResponse(path)


@app.post("/api/market/agents/{publication_id}/install", status_code=201)
async def install_market_agent(
    publication_id: str, payload: AgentInstall, request: Request
):
    owner_id = _user_id(request)
    publication = store.get_agent_publication(publication_id)
    if not publication:
        raise HTTPException(404, "Published Agent not found")
    version = _normalize_agent_version(payload.version) if payload.version else None
    installed = store.install_agent_publication(publication_id, owner_id, version)
    if not installed:
        raise HTTPException(404, "Published Agent version not found")
    source_agent = store.get_agent(publication["source_agent_id"])
    if source_agent:
        avatar_path = copy_avatar(settings.data_dir, source_agent, installed["id"])
        if avatar_path:
            installed = (
                store.update_agent(installed["id"], {"avatar_path": avatar_path})
                or installed
            )
    return {"agent": installed}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str, request: Request):
    return _visible_or_404(store.get_agent(agent_id), request, "Agent")


@app.get("/api/agents/{agent_id}/avatar")
async def get_agent_avatar(agent_id: str, request: Request):
    agent = _visible_or_404(store.get_agent(agent_id), request, "Agent")
    path = avatar_file(settings.data_dir, agent)
    if not path:
        raise HTTPException(404, "Agent avatar not found")
    return FileResponse(path)


@app.put("/api/agents/{agent_id}/avatar")
async def upload_agent_avatar(agent_id: str, request: Request):
    _visible_or_404(store.get_agent(agent_id), request, "Agent")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > 5 * 1024 * 1024
        except ValueError:
            too_large = False
        if too_large:
            raise HTTPException(413, "Avatar must be 5 MB or smaller")
    body = await request.body()
    avatar_path = save_avatar(
        settings.data_dir,
        agent_id,
        request.headers.get("content-type", ""),
        body,
    )
    return store.update_agent(agent_id, {"avatar_path": avatar_path})


@app.patch("/api/agents/{agent_id}")
async def update_agent(agent_id: str, payload: AgentUpdate, request: Request):
    if payload.tools is not None and any(
        tool not in SUPPORTED_TOOLS for tool in payload.tools
    ):
        raise HTTPException(400, "Unsupported tool")
    catalog = discover_resources(settings.pi_home, settings.pi_cwd)
    if payload.extensions is not None and any(
        path not in {item["path"] for item in catalog["extensions"]}
        for path in payload.extensions
    ):
        raise HTTPException(400, "Unsupported extension path")
    if payload.skills is not None and any(
        path not in {item["path"] for item in catalog["skills"]}
        for path in payload.skills
    ):
        raise HTTPException(400, "Unsupported skill path")
    if payload.mcp_servers is not None and any(
        name not in {item["id"] for item in catalog["mcp_servers"]}
        for name in payload.mcp_servers
    ):
        raise HTTPException(400, "Unsupported MCP server")
    existing = _visible_or_404(store.get_agent(agent_id), request, "Agent")
    _validate_model_selection(
        payload.provider
        if "provider" in payload.model_fields_set
        else existing.get("provider"),
        payload.model if "model" in payload.model_fields_set else existing.get("model"),
        catalog,
    )
    _validate_thinking_level(
        payload.thinking_level
        if "thinking_level" in payload.model_fields_set
        else existing.get("thinking_level")
    )
    agent = store.update_agent(agent_id, payload.model_dump(exclude_unset=True))
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


def _validate_model_selection(
    provider: str | None, model: str | None, catalog: dict
) -> None:
    if not provider and not model:
        return
    selected = next(
        (item for item in catalog["providers"] if item["id"] == provider), None
    )
    if not selected:
        raise HTTPException(400, "Unsupported provider")
    if not model or model not in {item["id"] for item in selected["models"]}:
        raise HTTPException(400, "Unsupported model for provider")


def _validate_thinking_level(level: str | None) -> None:
    if level and level not in {
        "off",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }:
        raise HTTPException(400, "Unsupported thinking level")


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, request: Request):
    agent = _visible_or_404(store.get_agent(agent_id), request, "Agent")
    if not store.delete_agent(agent_id):
        raise HTTPException(400, "Agent does not exist or is protected")
    remove_avatar(settings.data_dir, agent)
    return {"ok": True}


def title_for(content: str) -> str:
    return " ".join(content.split())[:48] or "New conversation"


SKILL_BLOCK_RE = re.compile(
    r'^<skill name="(?P<name>[^"]+)" location="(?P<location>[^"]+)">\n'
    r"[\s\S]*?\n</skill>(?:\n\n(?P<user_message>[\s\S]+))?$"
)


def _text_message_content(message: dict) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict) or not isinstance(part.get("text"), str):
            return None
        parts.append(part["text"])
    if not parts:
        return None
    return "".join(parts)


def _compact_skill_invocation(message: dict) -> dict | None:
    if message.get("role") != "user":
        return None
    text = _text_message_content(message)
    match = SKILL_BLOCK_RE.fullmatch(text) if text is not None else None
    if not match:
        return None
    name = match.group("name")
    user_message = (match.group("user_message") or "").strip()
    command = f"/skill:{name}"
    display_content = command + (f" {user_message}" if user_message else "")
    message["display_content"] = display_content
    message["_skill_invocation"] = {
        "name": name,
        "command": command,
        "user_message": user_message,
    }
    message["content"] = [{"type": "text", "text": display_content}]
    return message["_skill_invocation"]


def visible_messages(messages: list[dict], mode: str = "production") -> list[dict]:
    """Attach web activity results to calls while hiding raw process results."""
    results = {
        message.get("toolCallId"): message
        for message in messages
        if message.get("role") == "toolResult"
        and message.get("toolName") in {"web_search", "web_fetch"}
    }
    visible: list[dict] = []
    for original in messages:
        if original.get("role") == "toolResult" and original.get("toolName") in {
            "web_search",
            "web_fetch",
        }:
            continue
        message = copy.deepcopy(original)
        if message.get("role") == "assistant":
            for part in message.get("content") or []:
                if part.get("type") != "toolCall" or part.get("name") not in {
                    "web_search",
                    "web_fetch",
                }:
                    continue
                result = results.get(part.get("id"))
                if result:
                    part["webResult"] = result
                    arguments = part.get("arguments")
                    if isinstance(arguments, dict):
                        arguments["_webResult"] = result
                if message.get("timestamp") is not None:
                    part["_timestamp"] = message["timestamp"]
        _compact_skill_invocation(message)
        if mode != "development" and message.get("role") == "toolResult":
            continue
        visible.append(message)
    return visible


app.include_router(
    create_share_router(
        settings,
        store,
        runtime,
        _visible_or_404,
        _has_session_file,
        visible_messages,
    )
)


@app.get("/api/chats")
async def list_chats(request: Request):
    chats = [
        chat
        for chat in _visible_records(store.list_chats(), request)
        if chat.get("title") != "New conversation" or _has_session_file(chat)
    ]
    return {"chats": chats}


@app.post("/api/chats", status_code=201)
async def create_chat(payload: ChatCreate, request: Request):
    agent = _visible_or_404(store.get_agent(payload.agent_id), request, "Agent")
    # Pi accepts an externally supplied session id. The platform chat id is a UUID
    # and is therefore also a valid Pi session id.
    return store.create_chat(
        payload.agent_id,
        status="created",
        user_id=agent.get("user_id") or _user_id(request),
    )


@app.patch("/api/chats/{chat_id}")
async def update_chat(chat_id: str, payload: ChatUpdate, request: Request):
    if not payload.title.strip():
        raise HTTPException(422, "Chat title cannot be empty")
    _visible_or_404(store.get_chat(chat_id), request, "Chat")
    chat = store.update_chat(chat_id, {"title": payload.title.strip()})
    return chat


@app.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str, request: Request):
    chat = _visible_or_404(store.get_chat(chat_id), request, "Chat")
    if chat.get("title") == "New conversation" and not _has_session_file(chat):
        raise HTTPException(404, "Chat has not started")
    return chat


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    chat = _visible_or_404(store.get_chat(chat_id), request, "Chat")
    await runtime.close_chat(chat_id)
    session_id = chat.get("session_id") or chat_id
    session_paths = [
        path
        for path in settings.pi_session_dir.iterdir()
        if path.is_file() and path.name.endswith(f"_{session_id}.jsonl")
    ]
    if not session_paths:
        store.delete_chat(chat_id)
        return {"ok": True, "deleted_files": [], "deleted_sessions": []}
    messages: list[dict] = []
    try:
        messages = await runtime.messages(chat)
    except PiRpcError:
        messages = []
    protected_paths: set[str] = set()
    for other_chat in _visible_records(store.list_chats(), request):
        if other_chat["id"] == chat_id:
            continue
        try:
            other_messages = await runtime.messages(other_chat)
        except PiRpcError:
            continue
        protected_paths.update(
            item["path"]
            for item in discover_chat_files(other_messages, settings.pi_cwd)
        )
    deleted_files = delete_chat_files(messages, settings.pi_cwd, protected_paths)
    deleted_sessions = []
    for session_path in session_paths:
        try:
            session_path.unlink()
            deleted_sessions.append(session_path.name)
        except OSError:
            continue
    store.delete_chat(chat_id)
    return {
        "ok": True,
        "deleted_files": deleted_files,
        "deleted_sessions": deleted_sessions,
    }


@app.get("/api/chats/{chat_id}/messages")
async def get_messages(chat_id: str, request: Request, mode: str = "production"):
    chat = _visible_or_404(store.get_chat(chat_id), request, "Chat")
    if chat["status"] == "created":
        # No prompt yet: no Pi session exists for this chat.
        return {"messages": []}
    if not _has_session_file(chat):
        raise HTTPException(404, "Pi session not found for this chat")
    if runtime.active_turn(chat_id) is not None:
        # A turn is streaming: read the transcript from disk instead of
        # spawning a second pi process on the busy session. Refreshes and
        # shared links see everything persisted so far.
        session_file = runtime.newest_session_file(chat)
        messages = read_session_messages(session_file) if session_file else []
        return {"messages": visible_messages(messages, mode)}
    try:
        return {"messages": visible_messages(await runtime.messages(chat), mode)}
    except PiRpcError as exc:
        store.update_chat(chat_id, {"status": "error"})
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/chats/{chat_id}/files")
async def list_chat_files(chat_id: str, request: Request):
    chat = _visible_or_404(store.get_chat(chat_id), request, "Chat")
    if not _has_session_file(chat):
        return {"files": []}
    try:
        files = discover_chat_files(await runtime.messages(chat), settings.pi_cwd)
        return {"files": [{**file, "chat_id": chat_id} for file in files]}
    except PiRpcError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/chats/{chat_id}/files/content")
async def get_chat_file(chat_id: str, path: str, request: Request):
    chat = _visible_or_404(store.get_chat(chat_id), request, "Chat")
    if not _has_session_file(chat):
        raise HTTPException(404, "Pi session not found for this chat")
    try:
        messages = await runtime.messages(chat)
        file_path = resolve_chat_file(messages, settings.pi_cwd, path)
    except PiRpcError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not file_path:
        raise HTTPException(404, "File not found or not generated by this chat")
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(415, "File is not a readable UTF-8 text file") from exc
    return {"content": content}


@app.get("/api/library/files")
async def list_library_files(
    request: Request,
    search: str = "",
    agent_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    chats = _visible_records(store.list_chats(), request)

    def files_for_chat(chat: dict) -> list[dict]:
        session_id = chat.get("session_id") or chat["id"]
        session_paths = list(settings.pi_session_dir.glob(f"*_{session_id}.jsonl"))
        if not session_paths:
            return []
        files = discover_session_files(session_paths[0], settings.pi_cwd)
        agent = store.get_agent(chat["agent_id"]) or {}
        return [
            {
                **file,
                "chat_id": chat["id"],
                "agent_id": chat["agent_id"],
                "agent_name": agent.get("name", "unknown agent"),
            }
            for file in files
        ]

    files = [file for chat in chats for file in files_for_chat(chat)]
    query = search.strip().casefold()
    if agent_id:
        files = [file for file in files if file["agent_id"] == agent_id]
    if query:
        files = [
            file
            for file in files
            if query in file["name"].casefold() or query in file["path"].casefold()
        ]
    files.sort(key=lambda file: file["generated_at"], reverse=True)
    total = len(files)
    start = (page - 1) * page_size
    return {
        "files": files[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@app.get("/api/chats/{chat_id}/files/download")
async def download_chat_file(chat_id: str, path: str, request: Request):
    chat = _visible_or_404(store.get_chat(chat_id), request, "Chat")
    try:
        file_path = resolve_chat_file(
            await runtime.messages(chat), settings.pi_cwd, path
        )
    except PiRpcError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not file_path:
        raise HTTPException(404, "File not found or not generated by this chat")
    return FileResponse(
        file_path, filename=file_path.name, media_type="application/octet-stream"
    )


def _sse_data(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _absorb_turn_event(
    event: dict, text: str, tools: list[dict]
) -> tuple[str, list[dict]]:
    if event["type"] == "delta":
        text += event["delta"]
    elif event["type"] == "final":
        text = event["text"]
    elif event["type"] == "tool":
        tools.append(event)
    return text, tools


def _pump_failure_reason(turn: ActiveTurn) -> str | None:
    """Error from a crashed run task, so viewers fail instead of hanging."""
    task = turn.task
    if task is None or not task.done() or task.cancelled():
        return None
    exc = task.exception()
    if exc is None or turn.finished:
        return None
    return str(exc)


async def _turn_event_stream(
    turn: ActiveTurn,
    queue: asyncio.Queue,
    replay: list[dict],
) -> AsyncIterator[str]:
    """SSE view of a server-side turn: replay what already happened, then
    follow live events. Viewer disconnects only unsubscribe — the turn keeps
    running and stays resumable at GET /api/chats/{id}/stream."""
    text = ""
    tools: list[dict] = []
    try:
        for event in replay:
            text, tools = _absorb_turn_event(event, text, tools)
            yield _sse_data(event)
        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=SSE_KEEPALIVE_SECONDS
                )
            except TimeoutError:
                failure = _pump_failure_reason(turn)
                if failure is not None:
                    # The run task died with an unexpected error; surface it
                    # instead of streaming keepalives forever.
                    store.update_chat(turn.chat_id, {"status": "error"})
                    yield _sse_data({"type": "error", "error": failure})
                    return
                yield ": keepalive\n\n"
                continue
            if event is None:
                break
            text, tools = _absorb_turn_event(event, text, tools)
            yield _sse_data(event)
        failure = pi_terminal_failure(turn.final_event.get("messages", []))
        error = failure or turn.error
        if error:
            yield _sse_data({"type": "error", "error": error})
            return
        updated = store.get_chat(turn.chat_id)
        if not updated:
            return
        turn_messages = visible_messages(
            [
                message
                for message in turn.final_event.get("messages", [])
                if message.get("role") == "assistant"
                or message.get("role") == "toolResult"
            ],
            "development",
        )
        yield _sse_data(
            {
                "type": "complete",
                "chat": updated,
                "assistant": text,
                "tools": tools,
                "messages": turn_messages,
            }
        )
    finally:
        turn.unsubscribe(queue)


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@app.post("/api/chats/{chat_id}/messages")
async def send_message(
    chat_id: str, payload: MessageCreate, request: Request, mode: str = "production"
):
    chat = _visible_or_404(store.get_chat(chat_id), request, "Chat")
    store.update_chat(
        chat_id,
        {
            "status": "running",
            "last_activity_at": now_iso(),
            "title": title_for(payload.content)
            if chat["title"] == "New conversation"
            else chat["title"],
        },
    )
    try:
        turn = runtime.start_turn(
            chat,
            payload.content,
            session_name=title_for(payload.content)
            if chat["title"] == "New conversation"
            else None,
        )
    except PiRpcError as exc:
        if "busy" not in str(exc).casefold():
            store.update_chat(chat_id, {"status": "error"})
        raise HTTPException(503, str(exc)) from exc
    queue, replay = turn.subscribe()
    return StreamingResponse(
        _turn_event_stream(turn, queue, replay),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.get("/api/chats/{chat_id}/stream")
async def resume_chat_stream(chat_id: str, request: Request):
    """Replay + follow the active turn, so refreshes, shared links, and
    other tabs stay in sync. 204 when nothing is running."""
    _visible_or_404(store.get_chat(chat_id), request, "Chat")
    turn = runtime.active_turn(chat_id)
    if turn is None:
        return Response(status_code=204)
    queue, replay = turn.subscribe()
    return StreamingResponse(
        _turn_event_stream(turn, queue, replay),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post("/api/chats/{chat_id}/abort")
async def abort_chat(chat_id: str, request: Request):
    _visible_or_404(store.get_chat(chat_id), request, "Chat")
    await runtime.abort(chat_id)
    return {"ok": True}


static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/{path:path}")
async def spa(path: str):
    return FileResponse(static_dir / "index.html")
