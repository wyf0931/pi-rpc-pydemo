import os

os.environ.setdefault("OMA_ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("OMA_DEFAULT_USER_PASSWORD", "test-user-password")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "test-admin-password"},
        )
        assert response.status_code == 200
        yield test_client


@pytest.fixture
def temporary_agent(client):
    created_ids = []

    def create(payload):
        response = client.post("/api/agents", json=payload)
        if response.is_success:
            created_ids.append(response.json()["id"])
        return response

    yield create

    for agent_id in created_ids:
        client.delete(f"/api/agents/{agent_id}")
