"""Unit tests for webhook_handler."""
from unittest.mock import MagicMock, patch, AsyncMock
import json

import pytest

from crew_jira_connector.ai_classifier import ClassificationResult
from crew_jira_connector.webhook_handler import (
    _get_description,
    _get_issue_key,
    _get_project_key,
    _get_status_name,
    _get_summary,
    process_webhook,
)


def _make_payload(
    key="PROJ-42",
    summary="Add pagination to user API",
    description="Implement paginated GET /api/users",
    status="Ready for Dev",
    project="PROJ",
    issue_type="Story",
):
    return {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": key,
            "fields": {
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
                "status": {"name": status},
                "project": {"key": project},
            },
        },
    }


def test_get_issue_key():
    assert _get_issue_key(_make_payload()) == "PROJ-42"
    assert _get_issue_key({}) is None


def test_get_project_key():
    assert _get_project_key(_make_payload()) == "PROJ"


def test_get_status_name():
    assert _get_status_name(_make_payload()) == "Ready for Dev"


def test_get_summary():
    assert _get_summary(_make_payload()) == "Add pagination to user API"


def test_get_description_plain():
    assert _get_description(_make_payload()) == "Implement paginated GET /api/users"


def test_get_description_adf():
    payload = _make_payload()
    payload["issue"]["fields"]["description"] = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello ADF"}]}
        ],
    }
    assert "Hello ADF" in _get_description(payload)


@pytest.mark.asyncio
async def test_process_webhook_status_filter(db):
    """Wrong status should skip."""
    payload = _make_payload(status="To Do")
    backend = MagicMock()
    with patch("crew_jira_connector.webhook_handler.get_settings") as mock_settings:
        mock_settings.return_value.jira_webhook_secret = ""
        mock_settings.return_value.jira_project_keys_list = []
        mock_settings.return_value.jira_trigger_status = "Ready for Dev"
        code, body = await process_webhook(payload, b"{}", None, backend, db)
    assert code == 200
    assert "skipped" in body


@pytest.mark.asyncio
async def test_process_webhook_content_too_short(db):
    """Short summary should fail content validation."""
    payload = _make_payload(summary="Fix", description="")
    backend = MagicMock()
    with patch("crew_jira_connector.webhook_handler.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.jira_webhook_secret = ""
        s.jira_project_keys_list = []
        s.jira_trigger_status = "Ready for Dev"
        s.max_vision_length = 50_000
        s.min_summary_length = 10
        s.allowed_git_hosts_list = ["github.com"]
        s.validate_repo_access = False
        code, body = await process_webhook(payload, b"{}", None, backend, db)
    assert code == 200
    assert "error" in body


@pytest.mark.asyncio
async def test_process_webhook_idempotency(db):
    """Duplicate issue should be skipped."""
    db.insert("PROJ-42", "existing-job", "build")
    payload = _make_payload()
    backend = MagicMock()
    with patch("crew_jira_connector.webhook_handler.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.jira_webhook_secret = ""
        s.jira_project_keys_list = []
        s.jira_trigger_status = "Ready for Dev"
        code, body = await process_webhook(payload, b"{}", None, backend, db)
    assert code == 200
    assert "duplicate" in body.get("skipped", "")
