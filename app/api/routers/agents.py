import re
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ...avatars import avatar_file, copy_avatar, remove_avatar, save_avatar
from ...config import Settings
from ...pi_rpc import PiRpcError, PiRuntimeManager
from ...resources import discover_resources
from ...store import SUPPORTED_TOOLS, Store


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


class AgentInstructionDraft(BaseModel):
    name: str = Field(default="", max_length=80)
    instruction: str = Field(default="", max_length=10000)
    provider: str | None = None
    model: str | None = None
    thinking_level: str | None = None
    tools: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)


class AgentPublish(BaseModel):
    version: str = Field(pattern=r"^v?\d+\.\d+\.\d+$")


class AgentInstall(BaseModel):
    version: str | None = Field(default=None, pattern=r"^v?\d+\.\d+\.\d+$")


def create_router(
    settings: Settings,
    store: Store,
    runtime: PiRuntimeManager,
    visible_or_404: Callable[[dict | None, Request, str], dict],
    visible_records: Callable[[list[dict], Request], list[dict]],
    user_id: Callable[[Request], str],
) -> APIRouter:
    router = APIRouter(tags=["agents"])

    def catalog() -> dict:
        return discover_resources(
            settings.pi_home, settings.pi_cwd, settings.pi_agents_home
        )

    def validate_capabilities(
        tools: list[str],
        extensions: list[str],
        skills: list[str],
        mcp_servers: list[str],
        resource_catalog: dict,
    ) -> None:
        if any(tool not in SUPPORTED_TOOLS for tool in tools):
            raise HTTPException(400, "Unsupported tool")
        allowed_extensions = {item["path"] for item in resource_catalog["extensions"]}
        allowed_skills = {item["path"] for item in resource_catalog["skills"]}
        allowed_servers = {item["id"] for item in resource_catalog["mcp_servers"]}
        if any(path not in allowed_extensions for path in extensions):
            raise HTTPException(400, "Unsupported extension path")
        if any(path not in allowed_skills for path in skills):
            raise HTTPException(400, "Unsupported skill path")
        if any(name not in allowed_servers for name in mcp_servers):
            raise HTTPException(400, "Unsupported MCP server")

    def normalize_agent_version(version: str) -> str:
        value = version.strip()
        if not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
            raise HTTPException(
                422, "Agent version must use SemVer, for example v1.0.0"
            )
        return value if value.startswith("v") else f"v{value}"

    def market_agent_view(publication: dict) -> dict:
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

    @router.get("/api/agents")
    async def list_agents(request: Request):
        return {"agents": visible_records(store.list_agents(), request)}

    @router.post("/api/agents", status_code=201)
    async def create_agent(payload: AgentCreate, request: Request):
        owner_id = user_id(request)
        if any(
            agent["name"].casefold() == payload.name.strip().casefold()
            for agent in visible_records(store.list_agents(), request)
        ):
            raise HTTPException(409, "Agent name already exists")
        tools = (
            payload.tools
            if payload.tools is not None
            else list(settings.pi_default_tools)
        )
        resource_catalog = catalog()
        validate_capabilities(
            tools,
            payload.extensions or [],
            payload.skills or [],
            payload.mcp_servers or [],
            resource_catalog,
        )
        validate_model_selection(payload.provider, payload.model, resource_catalog)
        validate_thinking_level(payload.thinking_level)
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

    @router.post("/api/agents/instruction-draft")
    async def generate_instruction(payload: AgentInstructionDraft):
        resource_catalog = catalog()
        validate_capabilities(
            payload.tools,
            payload.extensions,
            payload.skills,
            payload.mcp_servers,
            resource_catalog,
        )
        validate_model_selection(payload.provider, payload.model, resource_catalog)
        validate_thinking_level(payload.thinking_level)
        skill_by_path = {item["path"]: item for item in resource_catalog["skills"]}
        extension_by_path = {
            item["path"]: item for item in resource_catalog["extensions"]
        }
        mcp_by_id = {item["id"]: item for item in resource_catalog["mcp_servers"]}
        draft = {
            "agent_name": payload.name.strip(),
            "existing_instruction": payload.instruction.strip(),
            "provider": payload.provider,
            "model": payload.model,
            "thinking_level": payload.thinking_level,
            "tools": payload.tools,
            "extensions": [extension_by_path[path] for path in payload.extensions],
            "mcp_servers": [mcp_by_id[name] for name in payload.mcp_servers],
            "skills": payload.skills,
            "skill_catalog": [skill_by_path[path] for path in payload.skills],
        }
        try:
            instruction = await runtime.generate_agent_instruction(draft)
        except PiRpcError as exc:
            raise HTTPException(503, str(exc)) from exc
        return {"instruction": instruction}

    @router.get("/api/market/agents")
    async def list_market_agents():
        return {
            "agents": [
                market_agent_view(item) for item in store.list_agent_publications()
            ]
        }

    @router.post("/api/agents/{agent_id}/publish")
    async def publish_agent(agent_id: str, payload: AgentPublish, request: Request):
        agent = visible_or_404(store.get_agent(agent_id), request, "Agent")
        version = normalize_agent_version(payload.version)
        publication = next(
            (
                item
                for item in store.list_agent_publications()
                if item["source_agent_id"] == agent_id
            ),
            None,
        )
        if publication and store.has_agent_publication_version(
            publication["id"], version
        ):
            raise HTTPException(409, f"Agent version {version} already exists")
        published = store.publish_agent(agent, user_id(request), version)
        return {"agent": market_agent_view(published)}

    @router.get("/api/market/agents/{publication_id}/avatar")
    async def get_market_agent_avatar(publication_id: str):
        publication = store.get_agent_publication(publication_id)
        if not publication:
            raise HTTPException(404, "Published Agent not found")
        agent = store.get_agent(publication["source_agent_id"])
        path = avatar_file(settings.data_dir, agent) if agent else None
        if not path:
            raise HTTPException(404, "Published Agent avatar not found")
        return FileResponse(path)

    @router.post("/api/market/agents/{publication_id}/install", status_code=201)
    async def install_market_agent(
        publication_id: str, payload: AgentInstall, request: Request
    ):
        owner_id = user_id(request)
        publication = store.get_agent_publication(publication_id)
        if not publication:
            raise HTTPException(404, "Published Agent not found")
        version = normalize_agent_version(payload.version) if payload.version else None
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

    @router.get("/api/agents/{agent_id}")
    async def get_agent(agent_id: str, request: Request):
        return visible_or_404(store.get_agent(agent_id), request, "Agent")

    @router.get("/api/agents/{agent_id}/avatar")
    async def get_agent_avatar(agent_id: str, request: Request):
        agent = visible_or_404(store.get_agent(agent_id), request, "Agent")
        path = avatar_file(settings.data_dir, agent)
        if not path:
            raise HTTPException(404, "Agent avatar not found")
        return FileResponse(path)

    @router.put("/api/agents/{agent_id}/avatar")
    async def upload_agent_avatar(agent_id: str, request: Request):
        visible_or_404(store.get_agent(agent_id), request, "Agent")
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
            settings.data_dir, agent_id, request.headers.get("content-type", ""), body
        )
        return store.update_agent(agent_id, {"avatar_path": avatar_path})

    @router.patch("/api/agents/{agent_id}")
    async def update_agent(agent_id: str, payload: AgentUpdate, request: Request):
        resource_catalog = catalog()
        validate_capabilities(
            payload.tools or [],
            payload.extensions or [],
            payload.skills or [],
            payload.mcp_servers or [],
            resource_catalog,
        )
        existing = visible_or_404(store.get_agent(agent_id), request, "Agent")
        validate_model_selection(
            payload.provider
            if "provider" in payload.model_fields_set
            else existing.get("provider"),
            payload.model
            if "model" in payload.model_fields_set
            else existing.get("model"),
            resource_catalog,
        )
        validate_thinking_level(
            payload.thinking_level
            if "thinking_level" in payload.model_fields_set
            else existing.get("thinking_level")
        )
        agent = store.update_agent(agent_id, payload.model_dump(exclude_unset=True))
        if not agent:
            raise HTTPException(404, "Agent not found")
        return agent

    @router.delete("/api/agents/{agent_id}")
    async def delete_agent(agent_id: str, request: Request):
        agent = visible_or_404(store.get_agent(agent_id), request, "Agent")
        if not store.delete_agent(agent_id):
            raise HTTPException(400, "Agent does not exist or is protected")
        remove_avatar(settings.data_dir, agent)
        return {"ok": True}

    return router


def validate_model_selection(
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


def validate_thinking_level(level: str | None) -> None:
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
