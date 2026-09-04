import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...autopilots import AutopilotScheduler, next_run_at
from ...pi_rpc import PiRpcError, PiRuntimeManager
from ...store import Store, now_iso


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


def create_executor(
    store: Store, runtime: PiRuntimeManager
) -> Callable[[dict], Awaitable[None]]:
    async def execute(autopilot: dict) -> None:
        user_id = autopilot.get("user_id")
        chat = store.create_autopilot_chat(
            autopilot["agent_id"], autopilot["name"], user_id=user_id
        )
        run = store.create_autopilot_run(
            autopilot["id"], chat["id"], chat["id"], user_id=user_id
        )
        started = time.monotonic()
        prompt = (
            f"{autopilot['instruction'].strip()}\n\nCurrent time: "
            f"{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        try:
            async for _event in runtime.stream(
                chat, prompt, session_name=autopilot["name"]
            ):
                pass
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

    return execute


def create_router(
    store: Store,
    scheduler: AutopilotScheduler,
    visible_or_404: Callable[[dict | None, Request, str], dict],
    visible_records: Callable[[list[dict], Request], list[dict]],
    user_id: Callable[[Request], str],
) -> APIRouter:
    router = APIRouter(prefix="/api/autopilots", tags=["autopilots"])

    def view(item: dict) -> dict:
        agent = store.get_agent(item["agent_id"]) or {}
        upcoming = next_run_at(item)
        return {
            **item,
            "agent_name": agent.get("name", "Unknown agent"),
            "status": "active" if item.get("enabled") else "paused",
            "next_run_at": upcoming.isoformat() if upcoming else None,
        }

    @router.get("")
    async def list_autopilots(
        request: Request, search: str = "", agent_id: str | None = None
    ):
        query = search.strip().casefold()
        items = [
            view(item) for item in visible_records(store.list_autopilots(), request)
        ]
        if agent_id:
            items = [item for item in items if item["agent_id"] == agent_id]
        if query:
            items = [item for item in items if query in item["name"].casefold()]
        return {"autopilots": items}

    @router.post("", status_code=201)
    async def create_autopilot(payload: AutopilotCreate, request: Request):
        agent = visible_or_404(store.get_agent(payload.agent_id), request, "Agent")
        if next_run_at({"cron": payload.cron}) is None:
            raise HTTPException(400, "Invalid cron expression")
        return view(
            store.create_autopilot(
                payload.name,
                payload.instruction,
                payload.agent_id,
                payload.cron,
                payload.starts_at,
                payload.ends_at,
                user_id=agent.get("user_id") or user_id(request),
            )
        )

    @router.patch("/{autopilot_id}")
    async def update_autopilot(
        autopilot_id: str, payload: AutopilotUpdate, request: Request
    ):
        current = visible_or_404(
            store.get_autopilot(autopilot_id), request, "Autopilot"
        )
        values = payload.model_dump(exclude_unset=True)
        if "agent_id" in values:
            agent = visible_or_404(
                store.get_agent(values["agent_id"]), request, "Agent"
            )
            if agent.get("user_id") != current.get("user_id"):
                raise HTTPException(400, "Agent belongs to another user")
        if "cron" in values and next_run_at({"cron": values["cron"]}) is None:
            raise HTTPException(400, "Invalid cron expression")
        return view(store.update_autopilot(autopilot_id, values) or current)

    @router.delete("/{autopilot_id}")
    async def delete_autopilot(autopilot_id: str, request: Request):
        visible_or_404(store.get_autopilot(autopilot_id), request, "Autopilot")
        if not store.delete_autopilot(autopilot_id):
            raise HTTPException(404, "Autopilot not found")
        return {"ok": True}

    @router.post("/{autopilot_id}/run", status_code=202)
    async def run_autopilot(autopilot_id: str, request: Request):
        autopilot = visible_or_404(
            store.get_autopilot(autopilot_id), request, "Autopilot"
        )
        if autopilot_id in scheduler.running:
            raise HTTPException(409, "Autopilot is already running")
        store.update_autopilot(
            autopilot_id, {"last_run_at": datetime.now(UTC).isoformat()}
        )
        scheduler.running.add(autopilot_id)
        asyncio.create_task(scheduler._execute(autopilot))
        return {"ok": True, "status": "queued"}

    @router.get("/{autopilot_id}/runs")
    async def list_autopilot_runs(autopilot_id: str, request: Request):
        visible_or_404(store.get_autopilot(autopilot_id), request, "Autopilot")
        return {
            "runs": visible_records(store.list_autopilot_runs(autopilot_id), request)
        }

    return router
