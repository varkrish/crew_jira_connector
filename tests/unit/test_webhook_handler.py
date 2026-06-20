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


def _mock_settings_full():
    s = MagicMock()
    s.jira_webhook_secret = ""
    s.jira_project_keys_list = []
    s.jira_trigger_status = "Ready for Dev"
    s.max_vision_length = 50_000
    s.min_summary_length = 10
    s.allowed_git_hosts_list = ["github.com", "gitlab.com", "bitbucket.org"]
    s.validate_repo_access = False
    s.llm_api_base_url = "http://fake-llm"
    s.llm_api_key = "key"
    s.llm_model = "gpt-4o-mini"
    s.jira_mode_map_dict = {}
    s.jira_default_mode = "build"
    s.classifier_confidence_threshold = 0.5
    s.crew_studio_url = "http://fake-crew:8081"
    s.jira_base_url = "https://jira.example.com"
    s.jira_epic_issue_types_list = ["Epic"]
    s.jira_bug_issue_types_list = ["Bug"]
    s.jira_story_jql_template = '"Epic Link" = {epic_key} ORDER BY created ASC'
    return s


@pytest.mark.asyncio
async def test_process_webhook_epic_creates_job_with_stories(db):
    """Epic webhook fetches child stories and passes jira_stories metadata."""
    payload = _make_payload(
        key="EPIC-1",
        summary="Authentication Epic",
        description="Implement full auth flow",
        issue_type="Epic",
    )
    backend = MagicMock()

    from crew_jira_connector.epic_planner import StorySpec

    stories = [
        StorySpec(key="S-1", summary="Login", description="Login story", status="To Do", order=0),
        StorySpec(key="S-2", summary="Logout", description="Logout story", status="To Do", order=1),
    ]

    with patch("crew_jira_connector.webhook_handler.get_settings", return_value=_mock_settings_full()):
        with patch("crew_jira_connector.webhook_handler.get_epic_stories", return_value=stories):
            with patch("crew_jira_connector.webhook_handler.classify_issue", new_callable=AsyncMock) as mock_cls:
                mock_cls.return_value = ClassificationResult(
                    mode="build", repo_url=None, has_gherkin=False,
                    gherkin_features=[], confidence=0.9, reasoning="Epic build",
                )
                with patch("crew_jira_connector.webhook_handler.CrewClient") as mock_crew_cls:
                    mock_crew = MagicMock()
                    mock_crew.create_job.return_value = {"job_id": "epic-job-1"}
                    mock_crew_cls.return_value = mock_crew

                    code, body = await process_webhook(payload, b"{}", None, backend, db)

    assert code == 200
    assert body.get("job_id") == "epic-job-1"
    assert body.get("epic") is True
    call_kw = mock_crew.create_job.call_args[1]
    metadata = call_kw["metadata"]
    assert metadata["jira_epic_key"] == "EPIC-1"
    assert len(metadata["jira_stories"]) == 2
    assert metadata["jira_stories"][0]["key"] == "S-1"
    assert db.get_epic("EPIC-1") is not None


@pytest.mark.asyncio
async def test_process_webhook_epic_without_children_creates_job(db):
    """Epic with no linked stories still creates a Crew job for AI decomposition."""
    payload = _make_payload(
        key="EPIC-2",
        summary="Empty Epic",
        description="High level epic only",
        issue_type="Epic",
    )
    backend = MagicMock()

    with patch("crew_jira_connector.webhook_handler.get_settings", return_value=_mock_settings_full()):
        with patch("crew_jira_connector.webhook_handler.get_epic_stories", side_effect=ValueError("no stories")):
            with patch("crew_jira_connector.webhook_handler.classify_issue", new_callable=AsyncMock) as mock_cls:
                mock_cls.return_value = ClassificationResult(
                    mode="build", repo_url=None, has_gherkin=False,
                    gherkin_features=[], confidence=0.9, reasoning="Epic build",
                )
                with patch("crew_jira_connector.webhook_handler.CrewClient") as mock_crew_cls:
                    mock_crew = MagicMock()
                    mock_crew.create_job.return_value = {"job_id": "epic-job-empty"}
                    mock_crew_cls.return_value = mock_crew

                    code, body = await process_webhook(payload, b"{}", None, backend, db)

    assert code == 200
    assert body.get("job_id") == "epic-job-empty"
    metadata = mock_crew.create_job.call_args[1]["metadata"]
    assert metadata["jira_epic_key"] == "EPIC-2"
    assert metadata["jira_stories"] == []
    assert metadata["jira_project_key"] == "EPIC"


@pytest.mark.asyncio
async def test_process_webhook_bug_with_repo_creates_fix_job(db):
    """Bug + repo URL routes to mode=fix with auto_fix metadata."""
    payload = _make_payload(
        key="BUG-99",
        summary="Login fails on empty password",
        description="Repo: https://github.com/acme/app — steps to reproduce...",
        issue_type="Bug",
    )
    backend = MagicMock()

    with patch("crew_jira_connector.webhook_handler.get_settings", return_value=_mock_settings_full()):
        with patch("crew_jira_connector.webhook_handler.CrewClient") as mock_crew_cls:
            mock_crew = MagicMock()
            mock_crew.create_job.return_value = {"job_id": "fix-job-1"}
            mock_crew_cls.return_value = mock_crew

            code, body = await process_webhook(payload, b"{}", None, backend, db)

    assert code == 200
    assert body.get("mode") == "fix"
    call_kw = mock_crew.create_job.call_args[1]
    assert call_kw["mode"] == "fix"
    assert call_kw["metadata"]["work_intent"] == "fix"
    assert call_kw["metadata"]["auto_fix_after_analyze"] is True
    backend.add_comment.assert_called()


@pytest.mark.asyncio
async def test_process_webhook_bug_without_repo_skips(db):
    """Bug without repo URL should not create a job."""
    payload = _make_payload(
        key="BUG-100",
        summary="Something is broken badly",
        description="No repository link here",
        issue_type="Bug",
    )
    backend = MagicMock()

    with patch("crew_jira_connector.webhook_handler.get_settings", return_value=_mock_settings_full()):
        with patch("crew_jira_connector.webhook_handler.CrewClient") as mock_crew_cls:
            code, body = await process_webhook(payload, b"{}", None, backend, db)

    assert code == 200
    assert body.get("error") == "no repo url"
    mock_crew_cls.assert_not_called()
    backend.add_comment.assert_called()
