from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ...config import Settings
from ...store import Store
from ...usage import aggregate_usage


def create_router(settings: Settings, store: Store) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["usage"])

    @router.get("/usage")
    async def get_usage(
        request: Request,
        days: int | None = Query(default=None, ge=1, le=90),
        range_value: str | None = Query(
            default=None,
            alias="range",
            pattern=r"^[1-9][0-9]*d$",
        ),
    ) -> dict[str, Any]:
        user = request.state.user
        if not user:
            raise HTTPException(401, "Authentication required")
        if range_value:
            range_days = int(range_value[:-1])
            if range_days > 90:
                raise HTTPException(422, "Usage range cannot exceed 90 days")
            if days is not None and days != range_days:
                raise HTTPException(422, "Usage days and range parameters must match")
            days = range_days
        days = days or 7
        chats = store.list_chats()
        if user.get("role") != "admin":
            chats = [chat for chat in chats if chat.get("user_id") == user.get("id")]
        return aggregate_usage(
            chats,
            store.list_agents(),
            store.list_users(),
            settings.pi_session_dir,
            days=days,
            admin=user.get("role") == "admin",
        )

    return router
