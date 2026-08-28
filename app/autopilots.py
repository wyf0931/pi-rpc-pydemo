import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from croniter import croniter


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def next_run_at(autopilot: dict, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(UTC)
    starts_at = _parse_time(autopilot.get("starts_at"))
    ends_at = _parse_time(autopilot.get("ends_at"))
    if ends_at and now >= ends_at:
        return None
    base = max(now, starts_at) if starts_at else now
    try:
        candidate = croniter(autopilot["cron"], base).get_next(datetime)
    except (KeyError, ValueError, TypeError):
        return None
    if ends_at and candidate > ends_at:
        return None
    return candidate


def previous_run_at(autopilot: dict, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(UTC)
    try:
        return croniter(autopilot["cron"], now).get_prev(datetime)
    except (KeyError, ValueError, TypeError):
        return None


class AutopilotScheduler:
    def __init__(self, store, executor: Callable[[dict], Awaitable[None]], interval: float = 15.0):
        self.store = store
        self.executor = executor
        self.interval = interval
        self.task: asyncio.Task | None = None
        self.running: set[str] = set()

    async def start(self) -> None:
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def _loop(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self.interval)

    async def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        for autopilot in self.store.list_autopilots():
            if not autopilot.get("enabled") or autopilot["id"] in self.running:
                continue
            scheduled = previous_run_at(autopilot, now)
            starts_at = _parse_time(autopilot.get("starts_at"))
            ends_at = _parse_time(autopilot.get("ends_at"))
            last_run = _parse_time(autopilot.get("last_run_at"))
            created_at = _parse_time(autopilot.get("created_at"))
            if (scheduled and scheduled <= now and
                    (not starts_at or scheduled >= starts_at) and
                    (not ends_at or scheduled <= ends_at) and
                    (not created_at or scheduled > created_at) and
                    (not last_run or scheduled > last_run)):
                self.store.update_autopilot(autopilot["id"], {"last_run_at": scheduled.isoformat()})
                self.running.add(autopilot["id"])
                asyncio.create_task(self._execute(autopilot))

    async def _execute(self, autopilot: dict) -> None:
        try:
            await self.executor(autopilot)
        finally:
            self.running.discard(autopilot["id"])
