from collections.abc import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...config import Settings
from ...store import Store


class SystemTimezoneUpdate(BaseModel):
    timezone: str = Field(min_length=1, max_length=64)


def create_router(
    settings: Settings,
    store: Store,
    require_admin: Callable[[Request], dict],
) -> APIRouter:
    router = APIRouter(prefix="/api/settings", tags=["system-settings"])

    def system_timezone() -> str:
        return store.get_system_setting("timezone", settings.system_timezone)

    @router.get("")
    async def get_system_settings(request: Request):
        require_admin(request)
        return {"timezone": system_timezone()}

    @router.patch("/timezone")
    async def update_system_timezone(payload: SystemTimezoneUpdate, request: Request):
        require_admin(request)
        try:
            ZoneInfo(payload.timezone)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(422, "Timezone must be a valid IANA timezone") from exc
        return {"timezone": store.set_system_setting("timezone", payload.timezone)}

    return router
