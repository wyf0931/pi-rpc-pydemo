import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.storage import create_sqlite_engine, migrate_tinydb
from app.store import Store


def _legacy(path: Path, *, valid_relation: bool = True) -> None:
    user_id = "user-1"
    agent_id = "agent-1"
    data = {
        "users": {
            "1": {
                "id": user_id,
                "username": "admin",
                "email": None,
                "password_hash": "hash",
                "role": "admin",
                "status": "active",
                "created_at": "2026-01-01T00:00:00+00:00",
                "last_login_at": None,
            }
        },
        "agents": {
            "1": {
                "id": agent_id,
                "user_id": user_id,
                "name": "assistant",
                "instruction": "help",
                "provider": None,
                "model": None,
                "thinking_level": None,
                "extensions": [],
                "skills": [],
                "tools": [],
                "tools_configured": True,
                "mcp_servers": [],
                "avatar_path": None,
                "protected": True,
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        },
        "chats": {
            "1": {
                "id": "chat-1",
                "user_id": user_id,
                "session_id": "chat-1",
                "agent_id": agent_id if valid_relation else "missing",
                "title": "hello",
                "status": "ready",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "last_activity_at": "2026-01-01T00:00:00+00:00",
            }
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_migration_imports_all_tables_and_backs_up_source(tmp_path: Path):
    legacy = tmp_path / "platform.json"
    sqlite = tmp_path / "platform.sqlite3"
    _legacy(legacy)

    backup = migrate_tinydb(legacy, sqlite)

    assert backup is not None and backup.name.startswith("platform.json.")
    assert backup.read_bytes() == legacy.read_bytes()
    store = Store(legacy)
    agent = store.get_agent("agent-1")
    chat = store.get_chat("chat-1")
    assert agent is not None and agent["name"] == "assistant"
    assert chat is not None and chat["agent_id"] == "agent-1"
    assert store.list_users()[0]["username"] == "admin"

    assert migrate_tinydb(legacy, sqlite) is None
    assert len(list(tmp_path.glob("platform.json.*.bak"))) == 1


def test_failed_migration_preserves_source_and_leaves_no_sqlite(tmp_path: Path):
    legacy = tmp_path / "platform.json"
    sqlite = tmp_path / "platform.sqlite3"
    _legacy(legacy, valid_relation=False)
    original = legacy.read_bytes()

    with pytest.raises(ValueError, match="invalid relation"):
        migrate_tinydb(legacy, sqlite, strict=True)

    assert legacy.read_bytes() == original
    assert not sqlite.exists()
    assert not list(tmp_path.glob(".*.tmp"))
    assert not list(tmp_path.glob("platform.json.*.bak"))


def test_sqlite_allows_concurrent_writes(tmp_path: Path):
    path = tmp_path / "platform.json"
    Store(path).close()

    def create(index: int) -> str:
        store = Store(path)
        try:
            return store.create_user(f"user-{index}", None, "password")["id"]
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(create, range(32)))

    assert len(set(ids)) == 32
    store = Store(path)
    assert len(store.list_users()) == 32


def test_existing_sqlite_gets_agent_profile_columns(tmp_path: Path):
    path = tmp_path / "platform.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE agents (id TEXT PRIMARY KEY, name TEXT, instruction TEXT, created_at TEXT, updated_at TEXT, extra_json TEXT)"
    )
    connection.commit()
    connection.close()

    engine = create_sqlite_engine(path)
    with engine.connect() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(agents)")
        }
        version = connection.exec_driver_sql(
            "SELECT value FROM schema_meta WHERE key='version'"
        ).scalar()
    engine.dispose()
    assert {"description", "tags_json", "quickstarts_json"} <= columns
    assert version == "2"
