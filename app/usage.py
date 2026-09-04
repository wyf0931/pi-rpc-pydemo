"""Read-only usage aggregation over the platform's Pi session transcripts."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .files import read_session_messages

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "tool_calls",
    "search_calls",
    "fetch_calls",
    "cost",
)


def empty_usage() -> dict[str, int | float]:
    return {key: 0 for key in USAGE_KEYS}


def _number(value: Any, *, integer: bool = False) -> int | float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if integer:
        return int(number) if number >= 0 else 0
    return max(number, 0)


def _add_usage(target: dict[str, int | float], messages: list[dict]) -> None:
    for message in messages:
        if message.get("role") != "assistant":
            continue
        usage = message.get("usage")
        if isinstance(usage, dict):
            target["input_tokens"] += _number(usage.get("input"), integer=True)
            target["output_tokens"] += _number(usage.get("output"), integer=True)
            target["cached_tokens"] += _number(usage.get("cacheRead"), integer=True)
            cost = usage.get("cost")
            if isinstance(cost, dict):
                target["cost"] += _number(cost.get("total"))
        for part in message.get("content") or []:
            if not isinstance(part, dict) or part.get("type") != "toolCall":
                continue
            name = part.get("name")
            if name == "web_search":
                target["search_calls"] += 1
                target["tool_calls"] += 1
            elif name == "web_fetch":
                target["fetch_calls"] += 1
                target["tool_calls"] += 1


def usage_for_session(session_paths: list[Path]) -> dict[str, int | float]:
    """Aggregate supported fields from all transcript files for one session."""
    usage = empty_usage()
    for path in session_paths:
        _add_usage(usage, read_session_messages(path))
    return usage


def session_paths_for(session_dir: Path, session_id: str) -> list[Path]:
    if not session_id or not session_dir.is_dir():
        return []
    return sorted(
        (
            path
            for path in session_dir.iterdir()
            if path.is_file() and path.name.endswith(f"_{session_id}.jsonl")
        ),
        key=lambda path: path.name,
    )


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).date()


def _add_totals(target: dict[str, int | float], source: dict[str, Any]) -> None:
    for key in USAGE_KEYS:
        target[key] += source.get(key, 0)


def _row_with_usage(base: dict[str, Any], usage: dict[str, int | float]) -> dict:
    return {**base, **usage}


def aggregate_usage(
    chats: list[dict],
    agents: list[dict],
    users: list[dict],
    session_dir: Path,
    *,
    days: int = 7,
    today: date | None = None,
    admin: bool = False,
) -> dict[str, Any]:
    """Build the API payload for visible chats over a natural-day window."""
    today = today or datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    dates = [start + timedelta(days=index) for index in range(days)]
    daily = {
        item.isoformat(): {"date": item.isoformat(), "sessions": 0, **empty_usage()}
        for item in dates
    }
    agent_by_id = {item.get("id"): item for item in agents}
    user_by_id = {item.get("id"): item for item in users}
    summary: dict[str, int | float] = {"sessions": 0, **empty_usage()}
    session_rows: list[dict] = []
    user_totals: dict[str, dict[str, Any]] = {}
    agent_totals: dict[str, dict[str, Any]] = {}

    for chat in chats:
        chat_date = _parse_date(chat.get("created_at"))
        if chat_date is None or chat_date < start or chat_date > today:
            continue
        session_id = str(chat.get("session_id") or chat.get("id") or "")
        session_paths = session_paths_for(session_dir, session_id)
        # Match the sidebar history contract: an untouched placeholder chat
        # is metadata only and must not appear as a usage session.
        if chat.get("title") == "New conversation" and not session_paths:
            continue
        usage = usage_for_session(session_paths)
        agent = agent_by_id.get(chat.get("agent_id")) or {}
        user = user_by_id.get(chat.get("user_id")) or {}
        row = _row_with_usage(
            {
                "id": chat.get("id"),
                "session_id": session_id,
                "title": chat.get("title") or "New conversation",
                "created_at": chat.get("created_at"),
                "agent_id": chat.get("agent_id"),
                "agent_name": agent.get("name") or "Unknown agent",
                "user_id": chat.get("user_id"),
                "username": user.get("username") or "Unknown user",
            },
            usage,
        )
        session_rows.append(row)
        summary["sessions"] += 1
        _add_totals(summary, usage)
        day = daily[chat_date.isoformat()]
        day["sessions"] += 1
        _add_totals(day, usage)

        if admin:
            user_id = str(chat.get("user_id") or "unknown")
            user_row = user_totals.setdefault(
                user_id,
                {
                    "user_id": chat.get("user_id"),
                    "username": user.get("username") or "Unknown user",
                    "sessions": 0,
                    **empty_usage(),
                },
            )
            user_row["sessions"] += 1
            _add_totals(user_row, usage)
            agent_id = str(chat.get("agent_id") or "unknown")
            agent_row = agent_totals.setdefault(
                agent_id,
                {
                    "agent_id": chat.get("agent_id"),
                    "agent_name": agent.get("name") or "Unknown agent",
                    "sessions": 0,
                    **empty_usage(),
                },
            )
            agent_row["sessions"] += 1
            _add_totals(agent_row, usage)

    session_rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    payload: dict[str, Any] = {
        "range": {
            "days": days,
            "from": start.isoformat(),
            "to": today.isoformat(),
        },
        "summary": summary,
        "daily": list(daily.values()),
        "sessions": session_rows,
    }
    if admin:
        payload["users"] = sorted(
            user_totals.values(), key=lambda row: (-row["sessions"], row["username"])
        )
        payload["agents"] = sorted(
            agent_totals.values(),
            key=lambda row: (-row["sessions"], row["agent_name"]),
        )
    return payload
