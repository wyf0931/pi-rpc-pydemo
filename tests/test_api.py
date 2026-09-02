from uuid import uuid4

from app.main import pi_terminal_failure, visible_messages


def test_pi_terminal_failure_distinguishes_failed_and_successful_turns():
    assert (
        pi_terminal_failure(
            [
                {
                    "role": "assistant",
                    "stopReason": "error",
                    "errorMessage": "upstream failed",
                }
            ]
        )
        == "upstream failed"
    )
    assert (
        pi_terminal_failure(
            [
                {
                    "role": "assistant",
                    "stopReason": "aborted",
                    "errorMessage": "Request aborted",
                }
            ]
        )
        == "Request aborted"
    )
    assert (
        pi_terminal_failure(
            [
                {
                    "role": "assistant",
                    "stopReason": "stop",
                    "content": [{"type": "text", "text": "done"}],
                }
            ]
        )
        is None
    )


def test_visible_messages_attaches_web_results_to_calls():
    messages = [
        {
            "role": "assistant",
            "timestamp": "2026-08-30T00:00:00Z",
            "content": [
                {
                    "type": "toolCall",
                    "id": "call-1",
                    "name": "web_search",
                    "arguments": {"query": "news"},
                }
            ],
        },
        {
            "role": "toolResult",
            "toolCallId": "call-1",
            "toolName": "web_search",
            "content": [{"type": "text", "text": "# Web Search: news"}],
        },
    ]

    visible = visible_messages(messages)

    assert len(visible) == 1
    assert visible[0]["content"][0]["webResult"]["toolName"] == "web_search"
    assert "_webResult" in visible[0]["content"][0]["arguments"]


def test_health_and_agents(client):
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/api/health").json()["active_processes"] == 0
    agents = client.get("/api/agents").json()["agents"]
    assert any(agent["name"] == "assistant" for agent in agents)


def test_request_id_is_propagated_and_generated(client):
    supplied = client.get("/api/health", headers={"X-Request-ID": "debug-123"})
    generated = client.get("/api/health")

    assert supplied.headers["X-Request-ID"] == "debug-123"
    assert generated.headers["X-Request-ID"]
    assert generated.headers["X-Request-ID"] != "debug-123"


def test_resources_expose_platform_web_tools(client):
    tools = {
        item["name"]: item for item in client.get("/api/resources").json()["tools"]
    }
    assert tools["web_fetch"]["source"] == "platform"
    assert tools["web_search"]["source"] == "platform"


def test_market_skill_search(client, monkeypatch):
    async def fake_search(query, owner=None):
        assert query == "python"
        assert owner == "acme"
        return [
            {
                "repo": "acme/skills",
                "skill": "python",
                "installs": "1K",
                "url": "https://skills.sh/acme/skills/python",
            }
        ]

    monkeypatch.setattr("app.main.search_skills", fake_search)
    response = client.post(
        "/api/market/skills/search",
        json={"query": "python", "owner": "acme"},
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["skill"] == "python"


def test_market_skill_install(client, monkeypatch):
    called = {}

    async def fake_install(source, skill):
        called.update(source=source, skill=skill)

    monkeypatch.setattr("app.main.install_skill", fake_install)
    response = client.post(
        "/api/market/skills/install",
        json={"source": "acme/skills", "skill": "python"},
    )
    assert response.status_code == 200
    assert called == {"source": "acme/skills", "skill": "python"}


def test_market_skill_install_rejects_already_installed(client, monkeypatch):
    async def fail_install(*args):
        raise AssertionError("duplicate skill must not reach the CLI")

    monkeypatch.setattr("app.main.install_skill", fail_install)
    monkeypatch.setattr(
        "app.main.discover_resources",
        lambda *args: {"skills": [{"name": "python", "source": "acme/skills"}]},
    )
    response = client.post(
        "/api/market/skills/install",
        json={"source": "acme/skills", "skill": "python"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Skill python is already installed"


def test_market_skill_install_rejects_unsafe_source(client, monkeypatch):
    async def fail_install(*args):
        raise AssertionError("unsafe source must not reach the CLI")

    monkeypatch.setattr("app.main.install_skill", fail_install)
    response = client.post(
        "/api/market/skills/install",
        json={"source": "../../repo", "skill": "python"},
    )
    assert response.status_code == 422


def test_market_extension_install(client, monkeypatch):
    called = {}

    async def fake_install(package):
        called["package"] = package

    monkeypatch.setattr("app.main.install_extension", fake_install)
    response = client.post(
        "/api/market/extensions/install",
        json={"package": "@scope/extension"},
    )
    assert response.status_code == 200
    assert called == {"package": "npm:@scope/extension"}


def test_market_extension_install_rejects_already_installed(client, monkeypatch):
    async def fail_install(*args):
        raise AssertionError("duplicate extension must not reach Pi")

    monkeypatch.setattr("app.main.install_extension", fail_install)
    monkeypatch.setattr(
        "app.main.discover_resources",
        lambda *args: {
            "extensions": [{"name": "pi-mcp-adapter", "source": "npm:pi-mcp-adapter"}]
        },
    )
    response = client.post(
        "/api/market/extensions/install",
        json={"package": "pi install npm:pi-mcp-adapter"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Extension pi-mcp-adapter is already installed"


def test_market_extension_install_rejects_command(client, monkeypatch):
    async def fail_install(*args):
        raise AssertionError("invalid package must not reach Pi")

    monkeypatch.setattr("app.main.install_extension", fail_install)
    response = client.post(
        "/api/market/extensions/install",
        json={"package": "pi-mcp-adapter; rm -rf /"},
    )
    assert response.status_code == 422


def test_market_extension_uninstall(client, monkeypatch):
    called = {}

    async def fake_uninstall(package):
        called["package"] = package

    monkeypatch.setattr("app.main.uninstall_extension", fake_uninstall)
    response = client.post(
        "/api/market/extensions/uninstall",
        json={"package": "npm:pi-mcp-adapter"},
    )
    assert response.status_code == 200
    assert called == {"package": "npm:pi-mcp-adapter"}


def test_market_local_extension_uninstall(client, monkeypatch):
    called = {}

    async def fake_resources():
        return {
            "extensions": [{"path": "/tmp/local-extension", "name": "local-extension"}]
        }

    def fake_remove(path, roots):
        called.update(path=path, roots=roots)

    monkeypatch.setattr(
        "app.main.discover_resources",
        lambda *args: {
            "extensions": [{"path": "/tmp/local-extension", "name": "local-extension"}]
        },
    )
    monkeypatch.setattr("app.main.uninstall_local_extension", fake_remove)
    response = client.post(
        "/api/market/extensions/uninstall",
        json={"path": "/tmp/local-extension"},
    )
    assert response.status_code == 200
    assert called["path"] == "/tmp/local-extension"


def test_market_skill_uninstall(client, monkeypatch):
    called = {}

    async def fake_uninstall(source, skill):
        called.update(source=source, skill=skill)

    monkeypatch.setattr("app.main.uninstall_skill", fake_uninstall)
    response = client.post(
        "/api/market/skills/uninstall",
        json={"source": "acme/skills", "skill": "python"},
    )
    assert response.status_code == 200
    assert called == {"source": "acme/skills", "skill": "python"}


def test_market_skill_uninstall_without_source(client, monkeypatch):
    called = {}

    async def fake_uninstall(source, skill):
        called.update(source=source, skill=skill)

    monkeypatch.setattr("app.main.uninstall_skill", fake_uninstall)
    response = client.post(
        "/api/market/skills/uninstall",
        json={"skill": "local-skill"},
    )
    assert response.status_code == 200
    assert called == {"source": None, "skill": "local-skill"}


def test_create_agent_and_missing_chat(client, temporary_agent):
    response = temporary_agent(
        {"name": f"writer-{uuid4()}", "instruction": "Write clearly"}
    )
    assert response.status_code == 201
    assert response.json()["name"].startswith("writer-")
    assert client.get("/api/chats/missing").status_code == 404


def test_default_avatar_and_agent_avatar_upload(client, temporary_agent):
    default = next(
        agent
        for agent in client.get("/api/agents").json()["agents"]
        if agent["name"] == "assistant"
    )
    assert default["avatar_path"] == "avatars/default-assistant.jpg"
    assert client.get(f"/api/agents/{default['id']}/avatar").status_code == 200

    created = temporary_agent(
        {"name": f"avatar-{uuid4()}", "instruction": "Use an avatar"}
    )
    agent_id = created.json()["id"]
    uploaded = client.put(
        f"/api/agents/{agent_id}/avatar",
        content=b"\xff\xd8\xfffake-jpeg",
        headers={"Content-Type": "image/jpeg"},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["avatar_path"].startswith("avatars/")
    served = client.get(f"/api/agents/{agent_id}/avatar")
    assert served.status_code == 200
    assert served.content.startswith(b"\xff\xd8\xff")


def test_fresh_chat_messages_are_empty(client):
    agents = client.get("/api/agents").json()["agents"]
    agent_id = next(a["id"] for a in agents if a["name"] == "assistant")
    chat = client.post("/api/chats", json={"agent_id": agent_id}).json()
    assert chat["status"] == "created"
    response = client.get(f"/api/chats/{chat['id']}/messages")
    assert response.status_code == 200
    assert response.json() == {"messages": []}


def test_autopilot_crud(client):
    agent_id = client.get("/api/agents").json()["agents"][0]["id"]
    created = client.post(
        "/api/autopilots",
        json={
            "name": "Daily brief",
            "instruction": "Summarize the day",
            "agent_id": agent_id,
            "cron": "0 9 * * *",
        },
    )
    assert created.status_code == 201
    autopilot_id = created.json()["id"]
    assert (
        client.get("/api/autopilots?search=daily").json()["autopilots"][0]["name"]
        == "Daily brief"
    )
    updated = client.patch(f"/api/autopilots/{autopilot_id}", json={"enabled": True})
    assert updated.status_code == 200 and updated.json()["status"] == "active"
    assert client.get(f"/api/autopilots/{autopilot_id}/runs").json()["runs"] == []
    assert client.delete(f"/api/autopilots/{autopilot_id}").status_code == 200


def test_delete_empty_chat_does_not_start_pi(client):
    agent_id = client.get("/api/agents").json()["agents"][0]["id"]
    chat = client.post("/api/chats", json={"agent_id": agent_id}).json()
    response = client.delete(f"/api/chats/{chat['id']}")
    assert response.status_code == 200
    assert client.get(f"/api/chats/{chat['id']}").status_code == 404


def test_empty_chat_is_hidden_from_history(client):
    agent_id = client.get("/api/agents").json()["agents"][0]["id"]
    chat = client.post("/api/chats", json={"agent_id": agent_id}).json()
    assert all(
        item["id"] != chat["id"] for item in client.get("/api/chats").json()["chats"]
    )
    assert client.get(f"/api/chats/{chat['id']}").status_code == 404


class _DummyClient:
    """Stand-in for PiRpcClient so turn tests never spawn a real pi process."""

    async def request(self, *args, **kwargs):
        return {}

    async def close(self):
        pass


def test_resume_stream_returns_204_without_active_turn(client, temporary_agent):
    agent_id = temporary_agent({"name": "resumer", "instruction": "x"}).json()["id"]
    chat = client.post("/api/chats", json={"agent_id": agent_id}).json()
    response = client.get(f"/api/chats/{chat['id']}/stream")
    assert response.status_code == 204


def test_turn_survives_viewer_disconnect(client, monkeypatch, temporary_agent):
    """A dropped SSE connection must not abort the run: refreshes and other
    tabs reconnect to the still-running turn instead of losing the answer."""
    import asyncio
    import time as time_module

    import app.main as main_module

    agent_id = temporary_agent({"name": "resilient", "instruction": "x"}).json()["id"]
    chat = client.post("/api/chats", json={"agent_id": agent_id}).json()

    class SlowClient(_DummyClient):
        async def stream_prompt(self, message):
            yield {"type": "delta", "delta": "partial"}
            await asyncio.sleep(1.2)
            yield {
                "type": "done",
                "event": {
                    "messages": [
                        {
                            "role": "assistant",
                            "stopReason": "stop",
                            "content": [{"type": "text", "text": "done"}],
                        }
                    ]
                },
            }

    async def fake_start(chat, create=False, register=True):
        return SlowClient()

    monkeypatch.setattr(main_module.runtime, "_start", fake_start)

    with client.stream(
        "POST", f"/api/chats/{chat['id']}/messages", json={"content": "hi"}
    ) as response:
        for chunk in response.iter_text():
            if '"delta"' in chunk:
                break

    deadline = time_module.time() + 5
    status = ""
    while time_module.time() < deadline:
        status = client.get(f"/api/chats/{chat['id']}").json()["status"]
        if status == "ready":
            break
        time_module.sleep(0.2)
    assert status == "ready"
    client.delete(f"/api/chats/{chat['id']}")


def test_message_stream_sends_keepalive_when_idle(client, monkeypatch, temporary_agent):
    import asyncio

    import app.main as main_module

    agent_id = temporary_agent({"name": "heartbeat", "instruction": "x"}).json()["id"]
    chat = client.post("/api/chats", json={"agent_id": agent_id}).json()

    class IdleClient(_DummyClient):
        async def stream_prompt(self, message):
            yield {"type": "delta", "delta": "partial"}
            await asyncio.sleep(10)

    async def fake_start(chat, create=False, register=True):
        return IdleClient()

    monkeypatch.setattr(main_module.runtime, "_start", fake_start)
    monkeypatch.setattr(main_module, "SSE_KEEPALIVE_SECONDS", 0.2)

    chunks = []
    with client.stream(
        "POST", f"/api/chats/{chat['id']}/messages", json={"content": "hi"}
    ) as response:
        for chunk in response.iter_text():
            chunks.append(chunk)
            if ": keepalive" in "".join(chunks):
                break
    assert any(": keepalive" in chunk for chunk in chunks)
    client.delete(f"/api/chats/{chat['id']}")


def test_finished_turn_subscribe_receives_end_sentinel():
    from app.pi_rpc import ActiveTurn

    turn = ActiveTurn("chat-1")
    turn.record({"type": "delta", "delta": "x"})
    turn.close()
    queue, replay = turn.subscribe()
    assert len(replay) == 1
    assert queue.get_nowait() is None


def test_share_flow_public_and_revoked(client, temporary_agent):
    agent_id = temporary_agent({"name": "sharer", "instruction": "x"}).json()["id"]
    chat = client.post("/api/chats", json={"agent_id": agent_id}).json()

    created = client.post(f"/api/chats/{chat['id']}/share")
    assert created.status_code == 200
    token = created.json()["token"]
    assert created.json()["url"] == f"/share/{token}"

    # Idempotent: sharing again returns the same token.
    again = client.post(f"/api/chats/{chat['id']}/share")
    assert again.json()["token"] == token

    # Public read-only payload (no auth layer in tests; token is the gate).
    shared = client.get(f"/api/share/{token}")
    assert shared.status_code == 200
    assert shared.json()["messages"] == []
    assert shared.json()["chat"]["title"] == chat["title"]

    # The page itself is served for any token shape.
    assert client.get(f"/share/{token}").status_code == 200

    # Unknown tokens are 404.
    assert client.get("/api/share/not-a-token").status_code == 404

    # Deleting the chat revokes the share.
    client.delete(f"/api/chats/{chat['id']}")
    assert client.get(f"/api/share/{token}").status_code == 404


def test_chat_title_can_be_updated(client, temporary_agent):
    agent_id = temporary_agent({"name": "title-editor", "instruction": "x"}).json()[
        "id"
    ]
    chat = client.post("/api/chats", json={"agent_id": agent_id}).json()

    updated = client.patch(
        f"/api/chats/{chat['id']}", json={"title": "A renamed conversation"}
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "A renamed conversation"
    assert client.get(f"/api/chats/{chat['id']}").json()["title"] == (
        "A renamed conversation"
    )

    empty = client.patch(f"/api/chats/{chat['id']}", json={"title": "   "})
    assert empty.status_code == 422
    client.delete(f"/api/chats/{chat['id']}")


def test_shared_chat_files_endpoints(client, temporary_agent):
    agent_id = temporary_agent({"name": "fileshare", "instruction": "x"}).json()["id"]
    chat = client.post("/api/chats", json={"agent_id": agent_id}).json()
    token = client.post(f"/api/chats/{chat['id']}/share").json()["token"]

    # Chat without a Pi session yet: empty file list, still token-gated.
    listed = client.get(f"/api/share/{token}/files")
    assert listed.status_code == 200
    assert listed.json()["files"] == []
    assert (
        client.get(f"/api/share/{token}/files/content?path=research/x.md").status_code
        == 404
    )

    # Unknown tokens are rejected on both endpoints.
    assert client.get("/api/share/nope/files").status_code == 404
    assert client.get("/api/share/nope/files/content?path=x").status_code == 404

    # Deleting the chat revokes the share.
    client.delete(f"/api/chats/{chat['id']}")
    assert client.get(f"/api/share/{token}/files").status_code == 404
