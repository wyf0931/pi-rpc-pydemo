import json
from uuid import uuid4

from app import main as main_module


def test_usage_endpoint_scopes_normal_users_and_exposes_admin_dimensions(client):
    agent = client.get("/api/agents").json()["agents"][0]
    chat = client.post("/api/chats", json={"agent_id": agent["id"]}).json()
    session_path = main_module.settings.pi_session_dir / f"test_{chat['id']}.jsonl"
    session_path.write_text(
        json.dumps(
            {
                "message": {
                    "role": "assistant",
                    "usage": {
                        "input": 12,
                        "output": 4,
                        "cacheRead": 3,
                        "cost": {"total": 0.125},
                    },
                    "content": [
                        {"type": "toolCall", "name": "web_search", "id": "call-1"}
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    username = f"usage-normal-{uuid4().hex[:8]}"
    created = client.post("/api/users", json={"username": username})
    assert created.status_code == 201
    normal_user = created.json()
    assert normal_user

    try:
        admin_response = client.get("/api/usage?range=7d")
        assert admin_response.status_code == 200
        admin_payload = admin_response.json()
        assert admin_payload["summary"]["sessions"] >= 1
        assert admin_payload["summary"]["input_tokens"] >= 12
        assert admin_payload["summary"]["search_calls"] >= 1
        assert admin_payload["users"]
        assert admin_payload["agents"]
        assert any(row["id"] == chat["id"] for row in admin_payload["sessions"])

        client.post("/api/auth/logout")
        login = client.post(
            "/api/auth/login",
            json={
                "username": normal_user["username"],
                "password": "test-user-password",
            },
        )
        assert login.status_code == 200
        normal_response = client.get("/api/usage?range=7d")
        assert normal_response.status_code == 200
        normal_payload = normal_response.json()
        assert normal_payload["summary"]["sessions"] == 0
        assert normal_payload["sessions"] == []
        assert "users" not in normal_payload
        assert "agents" not in normal_payload
    finally:
        client.post("/api/auth/logout")
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "test-admin-password"},
        )
        main_module.store.delete_chat(chat["id"])
        if session_path.exists():
            session_path.unlink()
        if normal_user:
            main_module.store.delete_user(normal_user["id"])
