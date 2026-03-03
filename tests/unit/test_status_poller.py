"""Unit tests for StatusPoller."""
from unittest.mock import MagicMock, patch

import pytest

from crew_jira_connector.status_poller import StatusPoller


@pytest.fixture
def poller(db):
    crew_client = MagicMock()
    jira_backend = MagicMock()
    return StatusPoller(db, crew_client, jira_backend, interval_seconds=1)


def test_poll_completed_job(poller, db):
    """Completed job should trigger comment + transition + mark done."""
    db.insert("PROJ-20", "j-1", "build")
    poller.crew_client.get_job_status.return_value = {
        "status": "completed",
        "current_phase": "done",
    }

    with patch("crew_jira_connector.status_poller.get_settings") as mock_s:
        mock_s.return_value.jira_transition_done = "Done"
        mock_s.return_value.jira_transition_failed = "Failed"
        poller._run_once()

    poller.jira_backend.add_comment.assert_called_once()
    assert "completed" in poller.jira_backend.add_comment.call_args[0][1]
    poller.jira_backend.transition.assert_called_once_with("PROJ-20", "Done")
    assert not db.has_active_job("PROJ-20")


def test_poll_failed_job(poller, db):
    """Failed job should trigger comment + Failed transition."""
    db.insert("PROJ-21", "j-2", "refactor")
    poller.crew_client.get_job_status.return_value = {
        "status": "failed",
        "error": "Build error",
    }

    with patch("crew_jira_connector.status_poller.get_settings") as mock_s:
        mock_s.return_value.jira_transition_done = "Done"
        mock_s.return_value.jira_transition_failed = "Failed"
        poller._run_once()

    poller.jira_backend.add_comment.assert_called_once()
    assert "failed" in poller.jira_backend.add_comment.call_args[0][1]
    poller.jira_backend.transition.assert_called_once_with("PROJ-21", "Failed")


def test_poll_running_job(poller, db):
    """Running job should not trigger transition."""
    db.insert("PROJ-22", "j-3", "build")
    poller.crew_client.get_job_status.return_value = {
        "status": "running",
        "current_phase": "dev",
    }

    with patch("crew_jira_connector.status_poller.get_settings") as mock_s:
        mock_s.return_value.jira_transition_done = "Done"
        mock_s.return_value.jira_transition_failed = "Failed"
        poller._run_once()

    poller.jira_backend.transition.assert_not_called()
    assert db.has_active_job("PROJ-22")


def test_poll_empty(poller):
    """No active jobs should not error."""
    with patch("crew_jira_connector.status_poller.get_settings") as mock_s:
        mock_s.return_value.jira_transition_done = "Done"
        mock_s.return_value.jira_transition_failed = "Failed"
        poller._run_once()

    poller.crew_client.get_job_status.assert_not_called()
