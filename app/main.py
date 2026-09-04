import logging
import re
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .api.routers.autopilots import (
    create_executor as create_autopilot_executor,
)
from .api.routers.autopilots import (
    create_router as create_autopilot_router,
)
from .api.routers.chats import (
    create_router as create_chat_router,
)
from .api.routers.chats import visible_messages
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
from .resources import discover_resources
from .store import (
    SUPPORTED_TOOLS,
)

context = create_context()
settings = context.settings
store = context.store
runtime = context.runtime

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
app.include_router(
    create_chat_router(
        settings,
        store,
        runtime,
        _visible_or_404,
        _visible_records,
        _user_id,
        lambda chat: _has_session_file(chat),
    )
)

static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/{path:path}")
async def spa(path: str):
    return FileResponse(static_dir / "index.html")
