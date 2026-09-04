from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ...auth import verify_password
from ...config import Settings
from ...store import Store

SESSION_COOKIE = "oma_session"


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str | None = Field(default=None, max_length=200)


class UserStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(active|disabled)$")


def _require_admin(request: Request) -> dict:
    user = request.state.user
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def create_router(settings: Settings, store: Store) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["identity"])

    @router.post("/auth/login")
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
            secure=request.headers.get("x-forwarded-proto", request.url.scheme)
            == "https",
        )
        return store.public_user(updated)

    @router.get("/auth/session")
    async def auth_session(request: Request):
        user = request.state.user
        return {"user": store.public_user(user) if user else None}

    @router.post("/auth/logout")
    async def logout(request: Request, response: Response):
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            store.delete_session(token)
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    @router.get("/users")
    async def list_users(request: Request):
        _require_admin(request)
        return {"users": store.list_users()}

    @router.post("/users", status_code=201)
    async def create_user(payload: UserCreate, request: Request):
        _require_admin(request)
        if not settings.default_user_password:
            raise HTTPException(500, "OMA_DEFAULT_USER_PASSWORD is not configured")
        username = payload.username.strip()
        if store.get_user_by_username(username):
            raise HTTPException(409, "Username already exists")
        user = store.create_user(
            username, payload.email, settings.default_user_password
        )
        return store.public_user(user)

    @router.patch("/users/{user_id}/status")
    async def update_user_status(
        user_id: str, payload: UserStatusUpdate, request: Request
    ):
        _require_admin(request)
        user = store.get_user(user_id)
        if not user:
            raise HTTPException(404, "User not found")
        if user.get("role") == "admin" and payload.status == "disabled":
            raise HTTPException(400, "The admin account cannot be disabled")
        updated = store.update_user_status(user_id, payload.status)
        return store.public_user(updated or user)

    @router.delete("/users/{user_id}")
    async def delete_user(user_id: str, request: Request):
        _require_admin(request)
        user = store.get_user(user_id)
        if not user:
            raise HTTPException(404, "User not found")
        if user.get("role") == "admin":
            raise HTTPException(400, "The admin account cannot be deleted")
        store.delete_user(user_id)
        return {"ok": True}

    return router
