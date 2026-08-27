from pathlib import Path

from app.store import Store


def test_default_agent_and_agent_crud(tmp_path: Path):
    store = Store(tmp_path / "db.json")
    default = store.ensure_default_agent()
    assert default["name"] == "assistant"
    assert default["protected"] is True
    assert store.ensure_default_agent()["id"] == default["id"]

    agent = store.create_agent("researcher", "Research carefully", provider="deepseek", model="deepseek-v4-flash")
    assert store.get_agent(agent["id"])["instruction"] == "Research carefully"
    assert store.get_agent(agent["id"])["provider"] == "deepseek"
    assert store.get_agent(agent["id"])["model"] == "deepseek-v4-flash"
    assert store.update_agent(agent["id"], {"instruction": "Be rigorous"})["instruction"] == "Be rigorous"
    assert store.delete_agent(agent["id"]) is True
    assert store.delete_agent(default["id"]) is False


def test_chat_index_does_not_store_messages(tmp_path: Path):
    store = Store(tmp_path / "db.json")
    agent = store.ensure_default_agent()
    chat = store.create_chat(agent["id"], "session-1")
    assert chat["session_id"] == "session-1"
    assert "messages" not in chat
    assert "session_file" not in chat
