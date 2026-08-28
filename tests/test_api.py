from uuid import uuid4


def test_health_and_agents(client):
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/api/health").json()["active_processes"] == 0
    agents = client.get("/api/agents").json()["agents"]
    assert any(agent["name"] == "assistant" for agent in agents)


def test_create_agent_and_missing_chat(client, temporary_agent):
    response = temporary_agent(
        {"name": f"writer-{uuid4()}", "instruction": "Write clearly"}
    )
    assert response.status_code == 201
    assert response.json()["name"].startswith("writer-")
    assert client.get("/api/chats/missing").status_code == 404
