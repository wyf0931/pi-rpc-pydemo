import asyncio
import copy
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import verify_password
from .autopilots import AutopilotScheduler, next_run_at
from .avatars import avatar_file, remove_avatar, save_avatar, seed_default_avatar
from .config import get_settings
from .files import (
    delete_chat_files,
    discover_chat_files,
    discover_session_files,
    read_session_messages,
    resolve_chat_file,
)
from .market import (
    github_source_owner,
    install_extension,
    install_skill,
    normalize_npm_package,
    npm_package_name,
    preview_skills,
    search_skills,
    uninstall_extension,
    uninstall_local_extension,
    uninstall_skill,
    validate_skill_source,
)
from .observability import configure_logging, trace_request
from .pi_rpc import ActiveTurn, PiRpcError, PiRuntimeManager
from .resources import discover_resources
from .store import (
    SUPPORTED_TOOLS,
    Store,
    now_iso,
    pi_terminal_failure,
)

settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.pi_session_dir.mkdir(parents=True, exist_ok=True)
configure_logging(settings.log_dir)
store = Store(settings.data_dir / "platform.json")
default_agent = store.ensure_default_agent(list(settings.pi_default_tools))
if not default_agent.get("avatar_path"):
    seeded_agent = seed_default_avatar(settings.data_dir, default_agent)
    if seeded_agent.get("avatar_path"):
        store.update_agent(
            seeded_agent["id"], {"avatar_path": seeded_agent["avatar_path"]}
        )
runtime = PiRuntimeManager(settings, store)
if not settings.admin_password or not settings.default_user_password:
    raise RuntimeError(
        "OMA_ADMIN_PASSWORD and OMA_DEFAULT_USER_PASSWORD must be configured"
    )
admin_user = store.ensure_default_user(settings.admin_password)
if not default_agent.get("user_id"):
    default_agent = (
        store.update_agent(default_agent["id"], {"user_id": admin_user["id"]})
        or default_agent
    )

# SSE heartbeat cadence. Any proxy/browser idle timeout must be far larger
# than this (Cloudflare cuts idle streams at ~100s).
SSE_KEEPALIVE_SECONDS = 20.0
app = FastAPI(title="Pi Agent Platform")
app.middleware("http")(trace_request)
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
    user = request.state.user
    return bool(user and user.get("role") == "admin") or record.get(
        "user_id"
    ) == _user_id(request)


def _visible_or_404(record: dict | None, request: Request, label: str) -> dict:
    if not record or not _can_access(record, request):
        raise HTTPException(404, f"{label} not found")
    return record


def _visible_records(records: list[dict], request: Request) -> list[dict]:
    user = request.state.user
    if user and user.get("role") == "admin":
        return records
    user_id = _user_id(request)
    return [record for record in records if record.get("user_id") == user_id]


@app.middleware("http")
async def require_login(request: Request, call_next):
    user = _request_user(request)
    request.state.user = user
    if not user and not _is_auth_exempt(request.url.path):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return await call_next(request)


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


class SkillSearch(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    owner: str | None = Field(default=None, max_length=100)


class SkillInstall(BaseModel):
    source: str = Field(min_length=3, max_length=200)
    skill: str = Field(min_length=1, max_length=100)


class SkillPreview(BaseModel):
    source: str = Field(min_length=3, max_length=1000)


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str | None = Field(default=None, max_length=200)


class UserStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(active|disabled)$")


class SkillUninstall(BaseModel):
    source: str | None = Field(default=None, min_length=3, max_length=200)
    skill: str = Field(min_length=1, max_length=100)


class ExtensionPackage(BaseModel):
    package: str = Field(min_length=1, max_length=240)


class ExtensionUninstall(BaseModel):
    package: str | None = Field(default=None, min_length=1, max_length=240)
    path: str | None = Field(default=None, min_length=1, max_length=1000)


class AutopilotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=10000)
    agent_id: str
    cron: str = "0 * * * *"
    starts_at: str | None = None
    ends_at: str | None = None


class AutopilotUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    instruction: str | None = Field(default=None, min_length=1, max_length=10000)
    agent_id: str | None = None
    cron: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    enabled: bool | None = None


@app.on_event("startup")
async def startup():
    await scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    await scheduler.stop()
    await runtime.close()


@app.get("/api/health")
async def health():
    active_processes = sum(
        1
        for client in runtime.clients.values()
        if client.process and client.process.returncode is None
    )
    return {"ok": True, "active_processes": active_processes}


@app.post("/api/auth/login")
async def login(payload: LoginPayload, request: Request, response: Response):
    user = store.get_user_by_username(payload.username.strip())
    if (
        not user
        or user.get("status") != "active"
        or not verify_password(payload.password, user.get("password_hash", ""))
    ):
        raise HTTPException(401, "Invalid username or password")
    updated = store.mark_user_login(user["id"]) or user
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    token = store.create_session(user["id"], expires_at.isoformat())
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        max_age=24 * 60 * 60,
        samesite="lax",
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
    )
    return store.public_user(updated)


@app.get("/api/auth/session")
async def auth_session(request: Request):
    user = request.state.user
    return {"user": store.public_user(user) if user else None}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        store.delete_session(token)
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/users")
async def list_users(request: Request):
    _require_admin(request)
    return {"users": store.list_users()}


@app.post("/api/users", status_code=201)
async def create_user(payload: UserCreate, request: Request):
    _require_admin(request)
    if not settings.default_user_password:
        raise HTTPException(500, "OMA_DEFAULT_USER_PASSWORD is not configured")
    username = payload.username.strip()
    if store.get_user_by_username(username):
        raise HTTPException(409, "Username already exists")
    user = store.create_user(username, payload.email, settings.default_user_password)
    return store.public_user(user)


@app.patch("/api/users/{user_id}/status")
async def update_user_status(user_id: str, payload: UserStatusUpdate, request: Request):
    _require_admin(request)
    user = store.get_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.get("role") == "admin" and payload.status == "disabled":
        raise HTTPException(400, "The admin account cannot be disabled")
    updated = store.update_user_status(user_id, payload.status)
    return store.public_user(updated or user)


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    _require_admin(request)
    user = store.get_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.get("role") == "admin":
        raise HTTPException(400, "The admin account cannot be deleted")
    store.delete_user(user_id)
    return {"ok": True}


@app.get("/api/agents")
async def list_agents(request: Request):
    return {"agents": _visible_records(store.list_agents(), request)}


@app.get("/api/resources")
async def list_resources():
    catalog = discover_resources(settings.pi_home, settings.pi_cwd)
    catalog["default_provider"] = settings.pi_provider
    catalog["default_model"] = settings.pi_model
    catalog["default_tools"] = list(settings.pi_default_tools)
    catalog["tools"] = [
        {
            "name": name,
            "description": "Platform web tool"
            if name in {"web_fetch", "web_search"}
            else "Pi built-in tool",
            "source": "platform" if name in {"web_fetch", "web_search"} else "builtin",
        }
        for name in SUPPORTED_TOOLS
    ]
    catalog["default_extensions"] = list(settings.pi_default_extensions)
    catalog["default_skills"] = list(settings.pi_default_skills)
    catalog["default_mcp_servers"] = list(settings.pi_default_mcp_servers)
    catalog["mode"] = settings.mode
    catalog["default_thinking_level"] = settings.pi_thinking_level
    return catalog


@app.post("/api/market/skills/search")
async def market_skill_search(payload: SkillSearch):
    query = payload.query.strip()
    owner = payload.owner.strip() if payload.owner else None
    if not query:
        raise HTTPException(422, "Search query is required")
    logger.info(
        "market skill search",
        extra={"event": "market.skill.search", "operation": "search"},
    )
    try:
        results = await search_skills(query, owner)
    except TimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, f"skills search failed: {exc}") from exc
    return {"results": results}


@app.post("/api/market/skills/install")
async def market_skill_install(payload: SkillInstall, request: Request):
    _require_admin(request)
    source = payload.source.strip()
    skill = payload.skill.strip()
    logger.info(
        "market skill install",
        extra={"event": "market.skill.install", "operation": "install"},
    )
    try:
        validate_skill_source(source, skill)
        catalog = discover_resources(settings.pi_home, settings.pi_cwd)
        if any(item["name"] == skill for item in catalog["skills"]):
            raise HTTPException(409, f"Skill {skill} is already installed")
        await install_skill(source, skill)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, f"skill install failed: {exc}") from exc
    return {"skill": skill, "resources": await list_resources()}


@app.post("/api/market/skills/preview")
async def market_skill_preview(payload: SkillPreview):
    source = payload.source.strip()
    try:
        results = await preview_skills(source)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, f"skills preview failed: {exc}") from exc
    return {
        "results": [
            {
                "repo": source,
                "skill": item["skill"],
                "url": "",
                "installs": "",
                "owner": github_source_owner(source),
            }
            for item in results
        ]
    }


@app.post("/api/market/skills/uninstall")
async def market_skill_uninstall(payload: SkillUninstall, request: Request):
    _require_admin(request)
    source = payload.source.strip() if payload.source else None
    skill = payload.skill.strip()
    try:
        await uninstall_skill(source, skill)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, f"skill uninstall failed: {exc}") from exc
    return {"skill": skill, "resources": await list_resources()}


@app.post("/api/market/extensions/install")
async def market_extension_install(payload: ExtensionPackage, request: Request):
    _require_admin(request)
    try:
        package = normalize_npm_package(payload.package)
        package_name = npm_package_name(package)
        catalog = discover_resources(settings.pi_home, settings.pi_cwd)
        if any(
            item["name"] == package_name or item.get("source") == package
            for item in catalog["extensions"]
        ):
            raise HTTPException(409, f"Extension {package_name} is already installed")
        await install_extension(package)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, f"extension install failed: {exc}") from exc
    return {"package": package, "resources": await list_resources()}


@app.post("/api/market/extensions/uninstall")
async def market_extension_uninstall(payload: ExtensionUninstall, request: Request):
    _require_admin(request)
    try:
        if payload.package:
            package = normalize_npm_package(payload.package)
            await uninstall_extension(package)
        elif payload.path:
            catalog = discover_resources(settings.pi_home, settings.pi_cwd)
            discovered = next(
                (
                    item
                    for item in catalog["extensions"]
                    if item["path"] == payload.path
                ),
                None,
            )
            if not discovered:
                raise ValueError("Local extension is not a discovered resource")
            uninstall_local_extension(
                payload.path,
                [
                    settings.pi_home / "extensions",
                    settings.pi_cwd / ".pi" / "extensions",
                ],
            )
            package = discovered["name"]
        else:
            raise ValueError("Extension package or path is required")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, f"extension uninstall failed: {exc}") from exc
    return {"package": package, "resources": await list_resources()}


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
        if mode != "development" and message.get("role") == "toolResult":
            continue
        visible.append(message)
    return visible


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


def _autopilot_view(item: dict) -> dict:
    agent = store.get_agent(item["agent_id"]) or {}
    upcoming = next_run_at(item)
    return {
        **item,
        "agent_name": agent.get("name", "Unknown agent"),
        "status": "active" if item.get("enabled") else "paused",
        "next_run_at": upcoming.isoformat() if upcoming else None,
    }


async def execute_autopilot(autopilot: dict) -> None:
    user_id = autopilot.get("user_id")
    chat = store.create_autopilot_chat(
        autopilot["agent_id"], autopilot["name"], user_id=user_id
    )
    run = store.create_autopilot_run(
        autopilot["id"], chat["id"], chat["id"], user_id=user_id
    )
    started = time.monotonic()
    prompt = f"{autopilot['instruction'].strip()}\n\nCurrent time: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')}"
    try:
        async for _event in runtime.stream(
            chat, prompt, session_name=autopilot["name"]
        ):
            pass
        # Autopilot output is real activity: surface the chat in the sidebar.
        store.update_chat(chat["id"], {"last_activity_at": now_iso()})
        store.update_autopilot_run(
            run["id"],
            {
                "status": "success",
                "finished_at": datetime.now(UTC).isoformat(),
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
        store.update_chat(chat["id"], {"status": "ready"})
    except asyncio.CancelledError:
        store.update_autopilot_run(
            run["id"],
            {
                "status": "cancelled",
                "finished_at": datetime.now(UTC).isoformat(),
                "duration_ms": round((time.monotonic() - started) * 1000),
                "error": "Application stopped before the run completed",
            },
        )
        store.update_chat(chat["id"], {"status": "stopped"})
        raise
    except (PiRpcError, OSError, TimeoutError) as exc:
        store.update_autopilot_run(
            run["id"],
            {
                "status": "error",
                "finished_at": datetime.now(UTC).isoformat(),
                "duration_ms": round((time.monotonic() - started) * 1000),
                "error": str(exc),
            },
        )
        store.update_chat(chat["id"], {"status": "error"})


@app.get("/api/autopilots")
async def list_autopilots(
    request: Request, search: str = "", agent_id: str | None = None
):
    query = search.strip().casefold()
    items = [
        _autopilot_view(item)
        for item in _visible_records(store.list_autopilots(), request)
    ]
    if agent_id:
        items = [item for item in items if item["agent_id"] == agent_id]
    if query:
        items = [item for item in items if query in item["name"].casefold()]
    return {"autopilots": items}


@app.post("/api/autopilots", status_code=201)
async def create_autopilot(payload: AutopilotCreate, request: Request):
    agent = _visible_or_404(store.get_agent(payload.agent_id), request, "Agent")
    if next_run_at({"cron": payload.cron}) is None:
        raise HTTPException(400, "Invalid cron expression")
    return _autopilot_view(
        store.create_autopilot(
            payload.name,
            payload.instruction,
            payload.agent_id,
            payload.cron,
            payload.starts_at,
            payload.ends_at,
            user_id=agent.get("user_id") or _user_id(request),
        )
    )


@app.patch("/api/autopilots/{autopilot_id}")
async def update_autopilot(
    autopilot_id: str, payload: AutopilotUpdate, request: Request
):
    current = _visible_or_404(store.get_autopilot(autopilot_id), request, "Autopilot")
    values = payload.model_dump(exclude_unset=True)
    if "agent_id" in values:
        agent = _visible_or_404(store.get_agent(values["agent_id"]), request, "Agent")
        if agent.get("user_id") != current.get("user_id"):
            raise HTTPException(400, "Agent belongs to another user")
    if "cron" in values and next_run_at({"cron": values["cron"]}) is None:
        raise HTTPException(400, "Invalid cron expression")
    return _autopilot_view(store.update_autopilot(autopilot_id, values) or current)


@app.delete("/api/autopilots/{autopilot_id}")
async def delete_autopilot(autopilot_id: str, request: Request):
    _visible_or_404(store.get_autopilot(autopilot_id), request, "Autopilot")
    if not store.delete_autopilot(autopilot_id):
        raise HTTPException(404, "Autopilot not found")
    return {"ok": True}


@app.post("/api/autopilots/{autopilot_id}/run", status_code=202)
async def run_autopilot(autopilot_id: str, request: Request):
    autopilot = _visible_or_404(store.get_autopilot(autopilot_id), request, "Autopilot")
    if autopilot_id in scheduler.running:
        raise HTTPException(409, "Autopilot is already running")
    store.update_autopilot(autopilot_id, {"last_run_at": datetime.now(UTC).isoformat()})
    scheduler.running.add(autopilot_id)
    asyncio.create_task(scheduler._execute(autopilot))
    return {"ok": True, "status": "queued"}


@app.get("/api/autopilots/{autopilot_id}/runs")
async def list_autopilot_runs(autopilot_id: str, request: Request):
    _visible_or_404(store.get_autopilot(autopilot_id), request, "Autopilot")
    return {"runs": _visible_records(store.list_autopilot_runs(autopilot_id), request)}


scheduler = AutopilotScheduler(store, execute_autopilot)


static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.post("/api/chats/{chat_id}/share")
async def create_chat_share(chat_id: str, request: Request):
    """Create (or reuse) the unguessable public share token for a chat."""
    chat = _visible_or_404(store.get_chat(chat_id), request, "Chat")
    share = store.create_share(chat_id, user_id=chat.get("user_id"))
    return {"token": share["token"], "url": f"/share/{share['token']}"}


@app.get("/api/share/{token}")
async def get_shared_chat(token: str):
    """Public, read-only view of a shared chat — token is the only gate.

    The SPA route /share/{token} (served by the catch-all below) consumes
    this payload and renders the regular chat view in read-only mode."""
    share = store.get_share(token)
    if not share:
        raise HTTPException(404, "Share not found")
    chat = store.get_chat(share["chat_id"])
    if not chat:
        raise HTTPException(404, "Share not found")
    if chat["status"] != "created" and _has_session_file(chat):
        try:
            messages = await runtime.messages(chat)
        except PiRpcError as exc:
            raise HTTPException(503, str(exc)) from exc
    else:
        messages = []
    return {
        "chat": {
            "title": chat.get("title"),
            "created_at": chat.get("created_at"),
            "updated_at": chat.get("updated_at"),
            "agent_id": chat.get("agent_id"),
        },
        "messages": visible_messages(messages, "production"),
    }


@app.get("/api/share/{token}/files")
async def list_shared_chat_files(token: str):
    """Files generated by the shared chat's own write/edit tool calls,
    resolved inside PI_CWD — identical provenance rules as the owner
    endpoint, just gated by the share token instead of auth."""
    share = store.get_share(token)
    if not share:
        raise HTTPException(404, "Share not found")
    chat = store.get_chat(share["chat_id"])
    if not chat:
        raise HTTPException(404, "Share not found")
    session_file = runtime.newest_session_file(chat)
    files = (
        discover_session_files(session_file, settings.pi_cwd) if session_file else []
    )
    return {"files": files}


@app.get("/api/share/{token}/files/content")
async def get_shared_chat_file(token: str, path: str):
    share = store.get_share(token)
    if not share:
        raise HTTPException(404, "Share not found")
    chat = store.get_chat(share["chat_id"])
    if not chat:
        raise HTTPException(404, "Share not found")
    session_file = runtime.newest_session_file(chat)
    messages = read_session_messages(session_file) if session_file else []
    file_path = resolve_chat_file(messages, settings.pi_cwd, path)
    if not file_path:
        raise HTTPException(404, "File not found or not generated by this chat")
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(415, "File is not a readable UTF-8 text file") from exc
    return {"content": content}


@app.get("/{path:path}")
async def spa(path: str):
    return FileResponse(static_dir / "index.html")
