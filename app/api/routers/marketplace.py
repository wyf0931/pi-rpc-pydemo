import logging
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...config import Settings
from ...market import (
    McpServerExistsError,
    add_mcp_servers,
    github_source_owner,
    install_extension,
    install_skill,
    normalize_npm_package,
    npm_package_name,
    parse_mcp_config,
    preview_skills,
    remove_mcp_server,
    search_skills,
    uninstall_extension,
    uninstall_local_extension,
    uninstall_skill,
    validate_skill_source,
)
from ...resources import discover_resources


class SkillSearch(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    owner: str | None = Field(default=None, max_length=100)


class SkillInstall(BaseModel):
    source: str = Field(min_length=3, max_length=200)
    skill: str = Field(min_length=1, max_length=100)


class SkillPreview(BaseModel):
    source: str = Field(min_length=3, max_length=1000)


class SkillUninstall(BaseModel):
    source: str | None = Field(default=None, min_length=3, max_length=200)
    skill: str = Field(min_length=1, max_length=100)


class ExtensionPackage(BaseModel):
    package: str = Field(min_length=1, max_length=240)


class ExtensionUninstall(BaseModel):
    package: str | None = Field(default=None, min_length=1, max_length=240)
    path: str | None = Field(default=None, min_length=1, max_length=1000)


class McpServerConfig(BaseModel):
    config: str = Field(min_length=2, max_length=200_000)


def create_router(
    settings: Settings,
    require_admin: Callable[[Request], dict],
    resources: Callable[[], dict],
    logger: logging.Logger,
) -> APIRouter:
    router = APIRouter(prefix="/api/market", tags=["marketplace"])

    @router.post("/skills/search")
    async def skill_search(payload: SkillSearch):
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

    @router.post("/skills/install")
    async def skill_install(payload: SkillInstall, request: Request):
        require_admin(request)
        source = payload.source.strip()
        skill = payload.skill.strip()
        logger.info(
            "market skill install",
            extra={"event": "market.skill.install", "operation": "install"},
        )
        try:
            validate_skill_source(source, skill)
            catalog = discover_resources(
                settings.pi_home, settings.pi_cwd, settings.pi_agents_home
            )
            if any(item["name"] == skill for item in catalog["skills"]):
                raise HTTPException(409, f"Skill {skill} is already installed")
            await install_skill(source, skill, settings.pi_agents_home / "skills")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(504, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, f"skill install failed: {exc}") from exc
        return {"skill": skill, "resources": resources()}

    @router.post("/skills/preview")
    async def skill_preview(payload: SkillPreview):
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

    @router.post("/skills/uninstall")
    async def skill_uninstall(payload: SkillUninstall, request: Request):
        require_admin(request)
        source = payload.source.strip() if payload.source else None
        skill = payload.skill.strip()
        try:
            await uninstall_skill(source, skill, settings.pi_agents_home / "skills")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(504, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, f"skill uninstall failed: {exc}") from exc
        return {"skill": skill, "resources": resources()}

    @router.post("/extensions/install")
    async def extension_install(payload: ExtensionPackage, request: Request):
        require_admin(request)
        try:
            package = normalize_npm_package(payload.package)
            package_name = npm_package_name(package)
            catalog = discover_resources(
                settings.pi_home, settings.pi_cwd, settings.pi_agents_home
            )
            if any(
                item["name"] == package_name or item.get("source") == package
                for item in catalog["extensions"]
            ):
                raise HTTPException(
                    409, f"Extension {package_name} is already installed"
                )
            await install_extension(package)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(504, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, f"extension install failed: {exc}") from exc
        return {"package": package, "resources": resources()}

    @router.post("/extensions/uninstall")
    async def extension_uninstall(payload: ExtensionUninstall, request: Request):
        require_admin(request)
        try:
            if payload.package:
                package = normalize_npm_package(payload.package)
                await uninstall_extension(package)
            elif payload.path:
                catalog = discover_resources(
                    settings.pi_home, settings.pi_cwd, settings.pi_agents_home
                )
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
        return {"package": package, "resources": resources()}

    @router.post("/mcp-servers")
    async def mcp_server_add(payload: McpServerConfig, request: Request):
        require_admin(request)
        try:
            servers = parse_mcp_config(payload.config)
            added = add_mcp_servers(settings.pi_home / "mcp.json", servers)
        except McpServerExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                500, f"MCP configuration could not be saved: {exc}"
            ) from exc
        return {"servers": added, "resources": resources()}

    @router.delete("/mcp-servers/{name}")
    async def mcp_server_delete(name: str, request: Request):
        require_admin(request)
        try:
            remove_mcp_server(settings.pi_home / "mcp.json", name)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                500, f"MCP configuration could not be saved: {exc}"
            ) from exc
        return {"name": name, "resources": resources()}

    return router
