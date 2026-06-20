"""Tests for JIRA create_issue backend implementations."""

from unittest.mock import MagicMock, patch

import pytest

from crew_jira_connector.jira_backends.rest_backend import JiraRestBackend


def test_rest_backend_create_issue_cloud():
    backend = JiraRestBackend(
        base_url="https://jira.example.com",
        email="user@example.com",
        api_token="token",
    )
    backend._is_server = False

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"key": "PROJ-42"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(backend, "_request", return_value=mock_response) as req:
        key = backend.create_issue(
            project_key="PROJ",
            summary="Login API",
            description="Implement login endpoint",
            parent_key="PROJ-100",
        )

    assert key == "PROJ-42"
    req.assert_called_once()
    payload = req.call_args.kwargs["json"]
    assert payload["fields"]["project"]["key"] == "PROJ"
    assert payload["fields"]["parent"]["key"] == "PROJ-100"
    assert payload["fields"]["description"]["type"] == "doc"


def test_atlassian_mcp_create_issue():
    from crew_jira_connector.jira_backends.atlassian_mcp import AtlassianMCPBackend

    backend = AtlassianMCPBackend(api_token="tok")
    with patch.object(backend, "_call_tool", return_value={"key": "CLOUD-9"}) as tool:
        key = backend.create_issue("CLOUD", "Summary", "Desc", parent_key="CLOUD-1")
    assert key == "CLOUD-9"
    tool.assert_called_once()
    args = tool.call_args[0][1]
    assert args["parentKey"] == "CLOUD-1"
