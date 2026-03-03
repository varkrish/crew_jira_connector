"""API tests for the webhook endpoint via FastAPI test client."""
import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from crew_jira_connector.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root_endpoint(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "crew-jira-connector" in r.json()["service"]


def test_webhook_invalid_json(client):
    r = client.post("/webhooks/jira", content=b"not-json")
    assert r.status_code == 400


def test_webhook_empty_payload(client):
    r = client.post("/webhooks/jira", json={})
    assert r.status_code == 200


def test_webhook_wrong_status(client):
    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "TEST-1",
            "fields": {
                "summary": "Some issue",
                "description": "Some description",
                "issuetype": {"name": "Story"},
                "status": {"name": "To Do"},
                "project": {"key": "TEST"},
            },
        },
    }
    r = client.post("/webhooks/jira", json=payload)
    assert r.status_code == 200
    assert "skipped" in r.json()
