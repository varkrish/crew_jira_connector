"""Unit tests for CrewClient."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from crew_jira_connector.crew_client import CrewClient


@pytest.fixture
def client():
    return CrewClient("http://localhost:8081")


def test_create_job_build(client):
    """Build mode: single POST, no trigger."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"job_id": "j-123", "status": "queued"}
    mock_resp.raise_for_status = MagicMock()

    with patch("crew_jira_connector.crew_client.httpx.post", return_value=mock_resp) as mock_post:
        result = client.create_job(vision="Build a REST API", mode="build")
        assert result["job_id"] == "j-123"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["mode"] == "build"


def test_create_job_with_feature_files(client, tmp_path):
    """Multipart upload when .feature files are present."""
    feat = tmp_path / "features" / "login.feature"
    feat.parent.mkdir()
    feat.write_text("Feature: Login\n  Scenario: Valid login\n    Given a user\n    When they login\n    Then success")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"job_id": "j-456"}
    mock_resp.raise_for_status = MagicMock()

    with patch("crew_jira_connector.crew_client.httpx.post", return_value=mock_resp) as mock_post:
        result = client.create_job(
            vision="Build auth",
            mode="build",
            feature_files=[feat],
        )
        assert result["job_id"] == "j-456"
        call_kwargs = mock_post.call_args
        assert "files" in call_kwargs[1]


def test_trigger_refactor(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "running"}
    mock_resp.raise_for_status = MagicMock()

    with patch("crew_jira_connector.crew_client.httpx.post", return_value=mock_resp) as mock_post:
        result = client.trigger_refactor("j-123", target_stack="Java 17", instructions="Fix the bug")
        assert result["status"] == "running"
        assert "/api/jobs/j-123/refactor" in mock_post.call_args[0][0]


def test_trigger_migration(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "running"}
    mock_resp.raise_for_status = MagicMock()

    with patch("crew_jira_connector.crew_client.httpx.post", return_value=mock_resp) as mock_post:
        result = client.trigger_migration("j-789", migration_goal="Migrate to Quarkus")
        assert result["status"] == "running"
        assert "/api/jobs/j-789/migrate" in mock_post.call_args[0][0]


def test_get_job_status(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "completed", "current_phase": "done"}
    mock_resp.raise_for_status = MagicMock()

    with patch("crew_jira_connector.crew_client.httpx.get", return_value=mock_resp):
        result = client.get_job_status("j-123")
        assert result["status"] == "completed"
