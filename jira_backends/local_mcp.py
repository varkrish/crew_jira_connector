"""
Self-hosted MCP backend wrapping a local MCP server (cfdude/mcp-jira or jira-easy-mcp).
Communicates via STDIO or HTTP depending on configuration.
"""
import json
import logging
import subprocess
import threading
from typing import Optional

import httpx

from crew_jira_connector.jira_backends.base import JiraBackend

logger = logging.getLogger(__name__)


class LocalMCPBackend(JiraBackend):
    """Wraps a self-hosted Jira MCP server running locally or as a sidecar."""

    def __init__(
        self,
        mcp_command: Optional[str] = None,
        mcp_http_url: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ):
        """
        Args:
            mcp_command: STDIO command to launch MCP server (e.g. 'npx -y @cfdude/mcp-jira').
            mcp_http_url: HTTP URL if MCP server exposes an HTTP endpoint.
            env: Environment variables to pass to the MCP process.
        """
        self.mcp_command = mcp_command
        self.mcp_http_url = mcp_http_url.rstrip("/") if mcp_http_url else None
        self.env = env or {}
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._request_id = 0

    def _ensure_process(self) -> subprocess.Popen:
        """Start the MCP server process if using STDIO transport."""
        if self._process and self._process.poll() is None:
            return self._process
        if not self.mcp_command:
            raise RuntimeError("No mcp_command configured for STDIO transport")

        import os
        merged_env = {**os.environ, **self.env}
        self._process = subprocess.Popen(
            self.mcp_command.split(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
        )
        # Send initialize
        self._send_jsonrpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        return self._process

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send_jsonrpc(self, method: str, params: dict) -> dict:
        """Send JSON-RPC request via STDIO."""
        with self._lock:
            proc = self._ensure_process()
            msg = json.dumps({
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": method,
                "params": params,
            })
            proc.stdin.write((msg + "\n").encode())
            proc.stdin.flush()
            line = proc.stdout.readline().decode().strip()
            if not line:
                raise RuntimeError("No response from MCP server")
            return json.loads(line)

    def _call_tool_stdio(self, tool_name: str, arguments: dict) -> dict:
        result = self._send_jsonrpc("tools/call", {"name": tool_name, "arguments": arguments})
        if "error" in result:
            raise RuntimeError(f"MCP error: {result['error']}")
        content = result.get("result", {}).get("content", [])
        for block in content:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, KeyError):
                    return {"raw": block.get("text", "")}
        return result.get("result", {})

    def _call_tool_http(self, tool_name: str, arguments: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        with httpx.Client(timeout=30.0) as client:
            r = client.post(self.mcp_http_url, json=payload)
            r.raise_for_status()
            data = r.json()
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        content = data.get("result", {}).get("content", [])
        for block in content:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, KeyError):
                    return {"raw": block.get("text", "")}
        return data.get("result", {})

    def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        if self.mcp_http_url:
            return self._call_tool_http(tool_name, arguments)
        return self._call_tool_stdio(tool_name, arguments)

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

    def shutdown(self) -> None:
        """Terminate the MCP server process."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None
