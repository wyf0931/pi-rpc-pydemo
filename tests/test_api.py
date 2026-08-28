from uuid import uuid4


def test_health_and_agents(client):
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/api/health").json()["active_processes"] == 0
    agents = client.get("/api/agents").json()["agents"]
    assert any(agent["name"] == "assistant" for agent in agents)


def test_resources_expose_platform_web_tools(client):
    tools = {item["name"]: item for item in client.get("/api/resources").json()["tools"]}
    assert tools["web_fetch"]["source"] == "platform"
    assert tools["web_search"]["source"] == "platform"


def test_create_agent_and_missing_chat(client, temporary_agent):
    response = temporary_agent(
        {"name": f"writer-{uuid4()}", "instruction": "Write clearly"}
    )
    assert response.status_code == 201
    assert response.json()["name"].startswith("writer-")
    assert client.get("/api/chats/missing").status_code == 404
