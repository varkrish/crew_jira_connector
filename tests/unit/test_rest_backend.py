"""Unit tests for JiraRestBackend."""
from unittest.mock import patch, MagicMock

import pytest

from crew_jira_connector.jira_backends.rest_backend import JiraRestBackend


@pytest.fixture
def backend():
    return JiraRestBackend(
        base_url="https://mysite.atlassian.net",
        email="user@test.com",
        api_token="token123",
    )


def test_auth_header(backend):
    auth = backend._auth()
    assert auth is not None
    assert auth.startswith("Basic ")


def test_auth_username_password():
    b = JiraRestBackend(
        base_url="https://jira.local",
        username="admin",
        password="secret",
    )
    auth = b._auth()
    assert auth is not None
    assert auth.startswith("Basic ")


def test_get_issue(backend):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"key": "PROJ-1", "fields": {"summary": "Test"}}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(backend, "_request", return_value=mock_resp) as mock_req:
        result = backend.get_issue("PROJ-1")
        assert result["key"] == "PROJ-1"
        mock_req.assert_called_once_with("GET", "/rest/api/3/issue/PROJ-1")


def test_add_comment(backend):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch.object(backend, "_request", return_value=mock_resp) as mock_req:
        backend.add_comment("PROJ-1", "Job started")
        assert mock_req.call_count == 1
        args = mock_req.call_args
        assert "/comment" in args[0][1]


def test_transition_found(backend):
    transitions_resp = MagicMock()
    transitions_resp.json.return_value = {
        "transitions": [
            {"id": "31", "name": "Done"},
            {"id": "41", "name": "In Progress"},
        ]
    }
    transitions_resp.raise_for_status = MagicMock()

    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()

    with patch.object(backend, "_request", side_effect=[transitions_resp, post_resp]):
        backend.transition("PROJ-1", "Done")


def test_transition_not_found(backend):
    transitions_resp = MagicMock()
    transitions_resp.json.return_value = {
        "transitions": [{"id": "31", "name": "Done"}]
    }
    transitions_resp.raise_for_status = MagicMock()

    with patch.object(backend, "_request", return_value=transitions_resp):
        with pytest.raises(ValueError, match="not found"):
            backend.transition("PROJ-1", "Nonexistent")
