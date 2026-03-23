"""
E2E test: fake webhook -> process_webhook -> verify job created + Jira comment.
Uses mocked Crew Studio API and mocked Jira backend.
"""
import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from crew_jira_connector.db import IssueJobDB
from crew_jira_connector.webhook_handler import process_webhook


def _build_payload(
    key="PROJ-100",
    summary="Create a new inventory REST API",
    description="Build a CRUD API for managing warehouse inventory items with pagination support.",
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


@pytest.fixture
def e2e_db(tmp_path):
    return IssueJobDB(str(tmp_path / "e2e.db"))


def _mock_settings():
    s = MagicMock()
    s.jira_webhook_secret = ""
    s.jira_project_keys_list = []
    s.jira_trigger_status = "Ready for Dev"
    s.max_vision_length = 50_000
    s.min_summary_length = 10
    s.allowed_git_hosts_list = ["github.com", "gitlab.com", "bitbucket.org"]
    s.validate_repo_access = False
    s.llm_api_base_url = "http://fake-llm:1234"
    s.llm_api_key = "test-key"
    s.llm_model = "gpt-4o-mini"
    s.jira_mode_map_dict = {}
    s.jira_default_mode = "build"
    s.classifier_confidence_threshold = 0.5
    s.crew_studio_url = "http://fake-crew:8081"
    return s


@pytest.mark.asyncio
async def test_e2e_build_job(e2e_db):
    """Full flow: webhook -> classify -> create build job -> comment."""
    payload = _build_payload()
    backend = MagicMock()

    with patch("crew_jira_connector.webhook_handler.get_settings", return_value=_mock_settings()):
        with patch("crew_jira_connector.webhook_handler.classify_issue", new_callable=AsyncMock) as mock_cls:
            from crew_jira_connector.ai_classifier import ClassificationResult
            mock_cls.return_value = ClassificationResult(
                mode="build", repo_url=None, has_gherkin=False,
                gherkin_features=[], confidence=0.9, reasoning="New API",
            )
            with patch("crew_jira_connector.webhook_handler.CrewClient") as mock_crew_cls:
                mock_crew = MagicMock()
                mock_crew.create_job.return_value = {"job_id": "e2e-job-1"}
                mock_crew_cls.return_value = mock_crew

                code, body = await process_webhook(payload, b"{}", None, backend, e2e_db)

    assert code == 200
    assert body.get("job_id") == "e2e-job-1"
    assert body.get("mode") == "build"
    backend.add_comment.assert_called()
    assert e2e_db.has_active_job("PROJ-100")


@pytest.mark.asyncio
async def test_e2e_refactor_with_repo(e2e_db):
    """Refactor flow: classify -> create job -> trigger refactor -> comment."""
    payload = _build_payload(
        key="PROJ-101",
        summary="Fix NPE in UserService",
        description="Fix null pointer in https://github.com/acme/backend UserService.java",
        issue_type="Bug",
    )
    backend = MagicMock()

    with patch("crew_jira_connector.webhook_handler.get_settings", return_value=_mock_settings()):
        with patch("crew_jira_connector.webhook_handler.classify_issue", new_callable=AsyncMock) as mock_cls:
            from crew_jira_connector.ai_classifier import ClassificationResult
            mock_cls.return_value = ClassificationResult(
                mode="refactor",
                repo_url="https://github.com/acme/backend",
                has_gherkin=False,
                gherkin_features=[],
                confidence=0.85,
                reasoning="Bug fix",
            )
            with patch("crew_jira_connector.webhook_handler.CrewClient") as mock_crew_cls:
                mock_crew = MagicMock()
                mock_crew.create_job.return_value = {"job_id": "e2e-job-2"}
                mock_crew.trigger_refactor.return_value = {"status": "running"}
                mock_crew_cls.return_value = mock_crew

                code, body = await process_webhook(payload, b"{}", None, backend, e2e_db)

    assert code == 200
    assert body.get("mode") == "refactor"
    mock_crew.trigger_refactor.assert_called_once()


@pytest.mark.asyncio
async def test_e2e_vision_preserves_tech_stack_ac24_style(e2e_db):
    """AC-24 style: description with 'Spring Boot with PostgreSQL. Include OpenAPI docs.'
    Vision sent to Crew must contain that tech stack; metadata must include jira_issue_key."""
    summary = "Build a REST API for employee directory service"
    description = """Create a new microservice that provides CRUD endpoints for managing employee records.
- GET /api/employees - list all employees with pagination
- POST /api/employees - create new employee
- GET /api/employees/{id} - get employee by ID
- PUT /api/employees/{id} - update employee
- DELETE /api/employees/{id} - delete employee

Use Spring Boot with PostgreSQL. Include OpenAPI docs."""

    payload = _build_payload(
        key="AC-24",
        summary=summary,
        description=description,
        status="In Progress",
        project="AC",
        issue_type="Story",
    )
    backend = MagicMock()
    settings = _mock_settings()
    settings.jira_trigger_status = "In Progress"

    with patch("crew_jira_connector.webhook_handler.get_settings", return_value=settings):
        with patch("crew_jira_connector.webhook_handler.classify_issue", new_callable=AsyncMock) as mock_cls:
            from crew_jira_connector.ai_classifier import ClassificationResult
            mock_cls.return_value = ClassificationResult(
                mode="build",
                repo_url=None,
                has_gherkin=False,
                gherkin_features=[],
                confidence=0.9,
                reasoning="New API",
            )
            with patch("crew_jira_connector.webhook_handler.CrewClient") as mock_crew_cls:
                mock_crew = MagicMock()
                mock_crew.create_job.return_value = {"job_id": "ac24-job-1"}
                mock_crew_cls.return_value = mock_crew

                code, body = await process_webhook(payload, b"{}", None, backend, e2e_db)

    assert code == 200
    assert body.get("job_id") == "ac24-job-1"
    assert body.get("issue_key") == "AC-24"
    assert body.get("mode") == "build"

    # Vision sent to create_job must contain the tech stack from the description
    call_kw = mock_crew.create_job.call_args[1]
    vision = call_kw["vision"]
    assert "Spring Boot" in vision
    assert "PostgreSQL" in vision
    assert "OpenAPI" in vision
    assert "employee" in vision

    # Jira metadata must be passed for backtracking
    metadata = call_kw.get("metadata") or {}
    assert metadata.get("jira_issue_key") == "AC-24"
    assert "jira_issue_url" in metadata

    backend.add_comment.assert_called()
    assert e2e_db.has_active_job("AC-24")


def test_e2e_status_roundtrip(e2e_db):
    """Job completes -> poller syncs -> Jira comment + transition."""
    from crew_jira_connector.status_poller import StatusPoller

    e2e_db.insert("PROJ-200", "j-roundtrip", "build")
    crew_client = MagicMock()
    crew_client.get_job_status.return_value = {"status": "completed", "current_phase": "done"}
    jira_backend = MagicMock()
    poller = StatusPoller(e2e_db, crew_client, jira_backend, interval_seconds=1)

    with patch("crew_jira_connector.status_poller.get_settings") as mock_s:
        mock_s.return_value.jira_transition_done = "Done"
        mock_s.return_value.jira_transition_failed = "Failed"
        poller._run_once()

    jira_backend.add_comment.assert_called_once()
    assert "completed" in jira_backend.add_comment.call_args[0][1]
    jira_backend.transition.assert_called_once_with("PROJ-200", "Done")
    assert not e2e_db.has_active_job("PROJ-200")
