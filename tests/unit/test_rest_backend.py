"""Unit tests for JiraRestBackend."""
from unittest.mock import patch, MagicMock

import pytest

from crew_jira_connector.jira_backends.rest_backend import JiraRestBackend


@pytest.fixture
def cloud_backend():
    """Cloud backend (email + api_token) with detection pre-set."""
    b = JiraRestBackend(
        base_url="https://mysite.atlassian.net",
        email="user@test.com",
        api_token="token123",
    )
    b._is_server = False
    return b


@pytest.fixture
def server_backend():
    """Server backend (PAT) with detection pre-set."""
    b = JiraRestBackend(
        base_url="http://jira.local:8080",
        personal_access_token="my-pat-token",
    )
    b._is_server = True
    return b


# --- Auth ---

def test_auth_cloud(cloud_backend):
    auth = cloud_backend._auth()
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


def test_auth_pat():
    b = JiraRestBackend(
        base_url="http://jira.local:8080",
        personal_access_token="my-token",
    )
    assert b._auth() == "Bearer my-token"


def test_pat_takes_precedence_over_basic():
    b = JiraRestBackend(
        base_url="http://jira.local:8080",
        username="admin",
        password="secret",
        personal_access_token="my-token",
    )
    assert b._auth() == "Bearer my-token"


# --- Version detection ---

def test_detect_server():
    b = JiraRestBackend(base_url="http://jira.local:8080", personal_access_token="t")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"deploymentType": "Server", "version": "9.4.0"}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(b, "_request", return_value=mock_resp):
        b._detect_server()

    assert b._is_server is True
    assert b._api_version == "2"


def test_detect_cloud():
    b = JiraRestBackend(base_url="https://x.atlassian.net", email="a@b.com", api_token="t")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"deploymentType": "Cloud", "version": "1001.0.0"}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(b, "_request", return_value=mock_resp):
        b._detect_server()

    assert b._is_server is False
    assert b._api_version == "3"


def test_detect_failure_defaults_to_cloud():
    b = JiraRestBackend(base_url="http://bad-host", email="a@b.com", api_token="t")

    with patch.object(b, "_request", side_effect=Exception("connection refused")):
        b._detect_server()

    assert b._is_server is False
    assert b._api_version == "3"


def test_detection_cached():
    b = JiraRestBackend(base_url="http://jira.local:8080", personal_access_token="t")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"deploymentType": "Server", "version": "9.4.0"}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(b, "_request", return_value=mock_resp) as mock_req:
        b._detect_server()
        b._detect_server()
        assert mock_req.call_count == 1


# --- Cloud paths (api/3) ---

def test_get_issue_cloud(cloud_backend):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"key": "PROJ-1", "fields": {"summary": "Test"}}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(cloud_backend, "_request", return_value=mock_resp) as mock_req:
        result = cloud_backend.get_issue("PROJ-1")
        assert result["key"] == "PROJ-1"
        mock_req.assert_called_once_with("GET", "/rest/api/3/issue/PROJ-1")


def test_add_comment_cloud(cloud_backend):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch.object(cloud_backend, "_request", return_value=mock_resp) as mock_req:
        cloud_backend.add_comment("PROJ-1", "Job started")
        args, kwargs = mock_req.call_args
        assert args == ("POST", "/rest/api/3/issue/PROJ-1/comment")
        body = kwargs["json"]["body"]
        assert isinstance(body, dict)
        assert body["type"] == "doc"


def test_transition_cloud(cloud_backend):
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

    with patch.object(cloud_backend, "_request", side_effect=[transitions_resp, post_resp]) as mock_req:
        cloud_backend.transition("PROJ-1", "Done")
        calls = mock_req.call_args_list
        assert calls[0][0] == ("GET", "/rest/api/3/issue/PROJ-1/transitions")
        assert calls[1][0] == ("POST", "/rest/api/3/issue/PROJ-1/transitions")


# --- Server paths (api/2) ---

def test_get_issue_server(server_backend):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"key": "AC-1", "fields": {"summary": "Test"}}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(server_backend, "_request", return_value=mock_resp) as mock_req:
        result = server_backend.get_issue("AC-1")
        assert result["key"] == "AC-1"
        mock_req.assert_called_once_with("GET", "/rest/api/2/issue/AC-1")


def test_add_comment_server(server_backend):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with patch.object(server_backend, "_request", return_value=mock_resp) as mock_req:
        server_backend.add_comment("AC-1", "Job started")
        args, kwargs = mock_req.call_args
        assert args == ("POST", "/rest/api/2/issue/AC-1/comment")
        assert kwargs["json"]["body"] == "Job started"


def test_transition_server(server_backend):
    transitions_resp = MagicMock()
    transitions_resp.json.return_value = {
        "transitions": [
            {"id": "11", "name": "To Do"},
            {"id": "31", "name": "Done"},
        ]
    }
    transitions_resp.raise_for_status = MagicMock()
    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()

    with patch.object(server_backend, "_request", side_effect=[transitions_resp, post_resp]) as mock_req:
        server_backend.transition("AC-1", "Done")
        calls = mock_req.call_args_list
        assert calls[0][0] == ("GET", "/rest/api/2/issue/AC-1/transitions")
        assert calls[1][0] == ("POST", "/rest/api/2/issue/AC-1/transitions")


def test_transition_not_found(server_backend):
    transitions_resp = MagicMock()
    transitions_resp.json.return_value = {
        "transitions": [{"id": "31", "name": "Done"}]
    }
    transitions_resp.raise_for_status = MagicMock()

    with patch.object(server_backend, "_request", return_value=transitions_resp):
        with pytest.raises(ValueError, match="not found"):
            server_backend.transition("AC-1", "Nonexistent")
