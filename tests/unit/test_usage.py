import json
from datetime import date
from pathlib import Path

from app.usage import aggregate_usage, usage_for_session


def _write_session(path: Path, messages: list[dict], malformed: bool = False) -> None:
    lines = [json.dumps({"message": message}) for message in messages]
    if malformed:
        lines.insert(1, "not-json")
    path.write_text("\n".join(lines), encoding="utf-8")


def _assistant(input_tokens: int, *, tool: str | None = None) -> dict:
    content = []
    if tool:
        content.append({"type": "toolCall", "name": tool, "id": f"call-{tool}"})
    return {
        "role": "assistant",
        "usage": {
            "input": input_tokens,
            "output": 10,
            "cacheRead": 5,
            "cost": {"total": 0.25},
        },
        "content": content,
    }


def test_usage_for_session_ignores_malformed_lines_and_non_whitelisted_tools(
    tmp_path: Path,
):
    path = tmp_path / "2026-09-04_session.jsonl"
    _write_session(
        path,
        [
            _assistant(100, tool="web_search"),
            _assistant(50, tool="bash"),
            {"role": "user", "content": "hello"},
        ],
        malformed=True,
    )

    assert usage_for_session([path]) == {
        "input_tokens": 150,
        "output_tokens": 20,
        "cached_tokens": 10,
        "tool_calls": 1,
        "search_calls": 1,
        "fetch_calls": 0,
        "cost": 0.5,
    }


def test_aggregate_usage_buckets_sessions_and_admin_dimensions(tmp_path: Path):
    session_id = "chat-1"
    path = tmp_path / f"2026-09-04_{session_id}.jsonl"
    _write_session(path, [_assistant(100, tool="web_fetch")])
    chats = [
        {
            "id": session_id,
            "session_id": session_id,
            "title": "Research",
            "created_at": "2026-09-04T08:00:00+00:00",
            "agent_id": "agent-1",
            "user_id": "user-1",
        },
        {
            "id": "old-chat",
            "session_id": "old-chat",
            "title": "Outside range",
            "created_at": "2026-08-28T08:00:00+00:00",
            "agent_id": "agent-2",
            "user_id": "user-2",
        },
    ]
    agents = [{"id": "agent-1", "name": "Researcher"}]
    users = [{"id": "user-1", "username": "alice"}]

    payload = aggregate_usage(
        chats,
        agents,
        users,
        tmp_path,
        days=7,
        today=date(2026, 9, 4),
        admin=True,
    )

    assert payload["range"] == {
        "days": 7,
        "from": "2026-08-29",
        "to": "2026-09-04",
    }
    assert payload["summary"]["sessions"] == 1
    assert payload["summary"]["input_tokens"] == 100
    assert payload["summary"]["fetch_calls"] == 1
    assert payload["daily"][0]["date"] == "2026-08-29"
    assert payload["daily"][-1]["date"] == "2026-09-04"
    assert payload["daily"][-1]["sessions"] == 1
    assert payload["sessions"][0]["username"] == "alice"
    assert payload["users"][0]["username"] == "alice"
    assert payload["agents"][0]["agent_name"] == "Researcher"


def test_aggregate_usage_can_isolate_normal_user_chats(tmp_path: Path):
    chats = [
        {
            "id": "mine",
            "session_id": "mine",
            "created_at": "2026-09-04T00:00:00Z",
            "agent_id": "agent-1",
            "user_id": "user-1",
        },
        {
            "id": "theirs",
            "session_id": "theirs",
            "created_at": "2026-09-04T00:00:00Z",
            "agent_id": "agent-1",
            "user_id": "user-2",
        },
    ]
    visible = [chat for chat in chats if chat["user_id"] == "user-1"]

    payload = aggregate_usage(
        visible,
        [],
        [],
        tmp_path,
        today=date(2026, 9, 4),
    )

    assert [row["id"] for row in payload["sessions"]] == ["mine"]


def test_aggregate_usage_excludes_unstarted_new_conversations(tmp_path: Path):
    chats = [
        {
            "id": "empty",
            "session_id": "empty",
            "title": "New conversation",
            "created_at": "2026-09-04T10:00:00+00:00",
            "agent_id": "agent-1",
            "user_id": "user-1",
        },
        {
            "id": "started",
            "session_id": "started",
            "title": "New conversation",
            "created_at": "2026-09-04T11:00:00+00:00",
            "agent_id": "agent-1",
            "user_id": "user-1",
        },
    ]
    _write_session(
        tmp_path / "2026-09-04_started.jsonl",
        [_assistant(25)],
    )

    payload = aggregate_usage(
        chats,
        [{"id": "agent-1", "name": "assistant"}],
        [{"id": "user-1", "username": "alice"}],
        tmp_path,
        today=date(2026, 9, 4),
        admin=True,
    )

    assert [row["id"] for row in payload["sessions"]] == ["started"]
    assert payload["summary"]["sessions"] == 1
