from fastapi import APIRouter

from ...config import Settings
from ...resources import discover_resources
from ...store import SUPPORTED_TOOLS


def catalog_response(settings: Settings) -> dict:
    catalog = discover_resources(settings.pi_home, settings.pi_cwd)
    catalog["default_provider"] = settings.pi_provider
    catalog["default_model"] = settings.pi_model
    catalog["default_tools"] = list(settings.pi_default_tools)
    catalog["tools"] = [
        {
            "name": name,
            "description": "Platform artifact tool"
            if name == "publish_artifact"
            else "Platform web tool"
            if name in {"web_fetch", "web_search"}
            else "Pi built-in tool",
            "source": "platform"
            if name in {"web_fetch", "web_search", "publish_artifact"}
            else "builtin",
        }
        for name in SUPPORTED_TOOLS
    ]
    catalog["default_extensions"] = list(settings.pi_default_extensions)
    catalog["default_skills"] = list(settings.pi_default_skills)
    catalog["default_mcp_servers"] = list(settings.pi_default_mcp_servers)
    catalog["mode"] = settings.mode
    catalog["default_thinking_level"] = settings.pi_thinking_level
    return catalog


def create_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["resources"])

    @router.get("/resources")
    async def list_resources():
        return catalog_response(settings)

    return router
