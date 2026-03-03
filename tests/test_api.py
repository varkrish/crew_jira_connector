"""API tests for webhook and health endpoints."""
import json

import pytest
from fastapi.testclient import TestClient

from crew_jira_connector.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "crew-jira-connector" in r.json()["service"]


def test_webhook_invalid_json(client):
    r = client.post("/webhooks/jira", content=b"not json")
    assert r.status_code == 400


def test_webhook_skipped_no_issue(client):
    payload = {"webhookEvent": "jira:issue_updated"}
    r = client.post("/webhooks/jira", json=payload)
    assert r.status_code == 200
    assert "skipped" in r.json() or "error" in r.json()
