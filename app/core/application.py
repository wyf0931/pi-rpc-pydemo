from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from ..autopilots import AutopilotScheduler
from ..avatars import seed_default_avatar
from ..config import Settings, get_settings
from ..observability import configure_logging, trace_request
from ..pi_rpc import PiRuntimeManager
from ..store import Store


@dataclass
class ApplicationContext:
    """Process-scoped resources for OMA Studio's single-worker runtime."""

    settings: Settings
    store: Store
    runtime: PiRuntimeManager
    scheduler: AutopilotScheduler | None = None


def create_context() -> ApplicationContext:
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

    if not settings.admin_password or not settings.default_user_password:
        raise RuntimeError(
            "OMA_ADMIN_PASSWORD and OMA_DEFAULT_USER_PASSWORD must be configured"
        )
    admin_user = store.ensure_default_user(settings.admin_password)
    if not default_agent.get("user_id"):
        store.update_agent(default_agent["id"], {"user_id": admin_user["id"]})

    return ApplicationContext(
        settings=settings,
        store=store,
        runtime=PiRuntimeManager(settings, store),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    context: ApplicationContext = app.state.oma
    if context.scheduler is None:
        raise RuntimeError("Application scheduler was not configured")
    await context.scheduler.start()
    try:
        yield
    finally:
        await context.scheduler.stop()
        await context.runtime.close()


def create_app(context: ApplicationContext, **options: Any) -> FastAPI:
    app = FastAPI(title="Pi Agent Platform", lifespan=lifespan, **options)
    app.state.oma = context
    app.middleware("http")(trace_request)
    return app
