import logging
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
from .api.routers.usage import create_router as create_usage_router
from .autopilots import AutopilotScheduler
from .core.application import create_app, create_context
from .files import read_session_messages, resolve_chat_file
from .og import load_template, render_social_metadata

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
app.include_router(create_usage_router(settings, store))

static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

SPA_TEMPLATE = load_template(static_dir)
DEFAULT_OG_TITLE = "OMA Studio — AI Agent Platform"
DEFAULT_OG_DESCRIPTION = (
    "OMA Studio is a local-first platform for creating, managing, and collaborating "
    "with AI agents."
)


def _spa_page(
    request: Request,
    *,
    title: str = DEFAULT_OG_TITLE,
    description: str = DEFAULT_OG_DESCRIPTION,
) -> HTMLResponse:
    image_url = str(request.url_for("static", path="oma-logo-transparent.png"))
    html = render_social_metadata(
        SPA_TEMPLATE,
        title=title,
        description=description,
        canonical_url=str(request.url),
        image_url=image_url,
    )
    return HTMLResponse(html)


def _shared_chat(token: str) -> dict | None:
    share = store.get_share(token)
    if not share:
        return None
    chat = store.get_chat(share["chat_id"])
    return chat if chat else None


@app.get("/share/{token}", include_in_schema=False)
async def shared_spa(token: str, request: Request):
    chat = _shared_chat(token)
    if not chat:
        return _spa_page(request)
    chat_title = chat.get("title") or "Shared conversation"
    return _spa_page(
        request,
        title=f"{chat_title} — OMA Studio",
        description=f"View {chat_title} shared from OMA Studio.",
    )


@app.get("/file-view", include_in_schema=False)
async def file_view_spa(request: Request):
    token = request.query_params.get("share")
    path = request.query_params.get("path")
    chat = _shared_chat(token) if token else None
    if chat and path:
        session_file = runtime.newest_session_file(chat)
        messages = read_session_messages(session_file) if session_file else []
        file_path = resolve_chat_file(messages, settings.pi_cwd, path)
        if file_path:
            chat_title = chat.get("title") or "Shared conversation"
            return _spa_page(
                request,
                title=f"{file_path.name} — OMA Studio",
                description=(
                    f"Preview {file_path.name} from {chat_title} in OMA Studio."
                ),
            )
    return _spa_page(request)


@app.get("/{path:path}")
async def spa(request: Request, path: str):
    return _spa_page(request)
