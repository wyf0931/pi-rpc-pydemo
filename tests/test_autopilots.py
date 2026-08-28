import asyncio
from datetime import UTC, datetime

from app.autopilots import AutopilotScheduler, next_run_at
from app.store import Store


def test_naive_schedule_times_are_timezone_aware(tmp_path):
    value = next_run_at({"cron": "10 0 * * *", "starts_at": "2026-08-29T00:00"},
                        datetime(2026, 8, 29, 0, 1, tzinfo=UTC))
    assert value is not None and value.tzinfo is not None


def test_scheduler_recovers_stale_runs_on_start(tmp_path):
    store = Store(tmp_path / "platform.json")
    agent = store.ensure_default_agent()
    autopilot = store.create_autopilot("Daily", "Do work", agent["id"], "0 9 * * *")
    store.create_autopilot_run(autopilot["id"], "chat-1", "session-1")
    scheduler = AutopilotScheduler(store, lambda _item: asyncio.sleep(0))

    async def exercise():
        await scheduler.start()
        await scheduler.stop()

    asyncio.run(exercise())
    assert store.list_autopilot_runs(autopilot["id"])[0]["status"] == "cancelled"
