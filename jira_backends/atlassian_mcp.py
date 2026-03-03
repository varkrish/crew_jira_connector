"""
Atlassian hosted MCP backend for Jira Cloud.
Connects to https://mcp.atlassian.com/v1/mcp for richer search and operations.
"""
import json
import logging
from typing import Optional

import httpx

from crew_jira_connector.jira_backends.base import JiraBackend

logger = logging.getLogger(__name__)

MCP_ENDPOINT = "https://mcp.atlassian.com/v1/mcp"


class AtlassianMCPBackend(JiraBackend):
    """Talks to Atlassian's hosted MCP gateway (Jira Cloud only)."""

    def __init__(
        self,
        api_token: str,
        email: str = "",
        cloud_id: str = "",
        mcp_endpoint: str = MCP_ENDPOINT,
    ):
        self.api_token = api_token
        self.email = email
        self.cloud_id = cloud_id
        self.endpoint = mcp_endpoint.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Invoke an MCP tool via the Atlassian MCP gateway."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        with httpx.Client(timeout=30.0) as client:
            r = client.post(self.endpoint, headers=self._headers(), json=payload)
            r.raise_for_status()
            data = r.json()
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        result = data.get("result", {})
        # MCP returns content as a list of text blocks
        content_blocks = result.get("content", [])
        for block in content_blocks:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, KeyError):
                    return {"raw": block.get("text", "")}
        return result

    def get_issue(self, key: str) -> dict:
        return self._call_tool("jira_get_issue", {"issueKey": key})

    def add_comment(self, key: str, body: str) -> None:
        self._call_tool("jira_add_comment", {"issueKey": key, "comment": body})

    def transition(self, key: str, transition_name: str) -> None:
        self._call_tool(
            "jira_transition_issue",
            {"issueKey": key, "transitionName": transition_name},
        )

    def search(self, jql: str) -> list[dict]:
        result = self._call_tool("jira_search", {"jql": jql, "maxResults": 50})
        if isinstance(result, list):
            return result
        return result.get("issues", [])
