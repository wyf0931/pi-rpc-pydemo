from pathlib import Path

from app.store import Store


def test_default_agent_and_agent_crud(tmp_path: Path):
    store = Store(tmp_path / "db.json")
    default = store.ensure_default_agent()
    assert default["name"] == "assistant"
    assert default["protected"] is True
    assert store.ensure_default_agent()["id"] == default["id"]

    agent = store.create_agent(
        "researcher",
        "Research carefully",
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_level="low",
    )
    saved = store.get_agent(agent["id"])
    assert saved is not None
    assert saved["instruction"] == "Research carefully"
    assert saved["provider"] == "deepseek"
    assert saved["model"] == "deepseek-v4-flash"
    assert saved["thinking_level"] == "low"
    updated = store.update_agent(agent["id"], {"instruction": "Be rigorous"})
    assert updated is not None and updated["instruction"] == "Be rigorous"
    assert store.delete_agent(agent["id"]) is True
    assert store.delete_agent(default["id"]) is False


def test_chat_index_does_not_store_messages(tmp_path: Path):
    store = Store(tmp_path / "db.json")
    agent = store.ensure_default_agent()
    chat = store.create_chat(agent["id"], "session-1")
    assert chat["session_id"] == "session-1"
    assert "messages" not in chat
    assert "session_file" not in chat


def test_autopilot_chats_always_get_fresh_session_ids(tmp_path: Path):
    store = Store(tmp_path / "db.json")
    agent = store.ensure_default_agent()
    first = store.create_autopilot_chat(agent["id"], "Daily")
    second = store.create_autopilot_chat(agent["id"], "Daily")
    assert first["id"] != second["id"]
    assert first["session_id"] == first["id"]
    assert second["session_id"] == second["id"]


def test_new_chat_defaults_to_its_own_session_id(tmp_path: Path):
    store = Store(tmp_path / "db.json")
    agent = store.ensure_default_agent()
    chat = store.create_chat(agent["id"], status="created")
    assert chat["session_id"] == chat["id"]
    assert chat["session_id"] != "pending"


def test_autopilot_and_run_metadata(tmp_path: Path):
    store = Store(tmp_path / "db.json")
    agent = store.ensure_default_agent()
    autopilot = store.create_autopilot("Daily brief", "Summarize today", agent["id"], "0 9 * * *")
    assert store.list_autopilots()[0]["name"] == "Daily brief"
    run = store.create_autopilot_run(autopilot["id"], "chat-1", "session-1")
    store.update_autopilot_run(run["id"], {"status": "success", "duration_ms": 123})
    assert store.list_autopilot_runs(autopilot["id"])[0]["status"] == "success"
