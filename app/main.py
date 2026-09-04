import logging
import re
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routers.agents import create_router as create_agents_router
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
app.include_router(
    create_agents_router(settings, store, _visible_or_404, _visible_records, _user_id)
)
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



@app.get("/api/health")
async def health():
    active_processes = sum(
        1
        for client in runtime.clients.values()
        if client.process and client.process.returncode is None
    )
    return {"ok": True, "active_processes": active_processes}



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
