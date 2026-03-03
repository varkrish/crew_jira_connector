"""Jira REST API backend."""
import base64
from typing import Optional

import httpx

from crew_jira_connector.jira_backends.base import JiraBackend


class JiraRestBackend(JiraBackend):
    def __init__(
        self,
        base_url: str,
        email: str = "",
        api_token: str = "",
        username: str = "",
        password: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.username = username
        self.password = password

    def _auth(self) -> Optional[str]:
        if self.api_token and self.email:
            raw = f"{self.email}:{self.api_token}"
            return "Basic " + base64.b64encode(raw.encode()).decode()
        if self.username and self.password:
            raw = f"{self.username}:{self.password}"
            return "Basic " + base64.b64encode(raw.encode()).decode()
        return None

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        auth = self._auth()
        if auth:
            headers["Authorization"] = auth
        headers.setdefault("Accept", "application/json")
        headers.setdefault("Content-Type", "application/json")
        with httpx.Client(timeout=30.0) as client:
            return client.request(method, url, headers=headers, **kwargs)

    def get_issue(self, key: str) -> dict:
        r = self._request("GET", f"/rest/api/3/issue/{key}")
        r.raise_for_status()
        return r.json()

    def add_comment(self, key: str, body: str) -> None:
        r = self._request(
            "POST",
            f"/rest/api/3/issue/{key}/comment",
            json={"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}]}},
        )
        r.raise_for_status()

    def transition(self, key: str, transition_name: str) -> None:
        # Get available transitions
        r = self._request("GET", f"/rest/api/3/issue/{key}/transitions")
        r.raise_for_status()
        data = r.json()
        transitions = data.get("transitions", [])
        tid = None
        for t in transitions:
            if t.get("name", "").lower() == transition_name.lower():
                tid = t.get("id")
                break
        if not tid:
            raise ValueError(f"Transition '{transition_name}' not found for issue {key}")
        r = self._request("POST", f"/rest/api/3/issue/{key}/transitions", json={"transition": {"id": tid}})
        r.raise_for_status()
