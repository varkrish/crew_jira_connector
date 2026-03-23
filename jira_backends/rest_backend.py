"""Jira REST API backend with auto-detection for Server vs Cloud."""
import base64
import logging
from typing import Optional

import httpx

from crew_jira_connector.jira_backends.base import JiraBackend

logger = logging.getLogger(__name__)


class JiraRestBackend(JiraBackend):
    def __init__(
        self,
        base_url: str,
        email: str = "",
        api_token: str = "",
        username: str = "",
        password: str = "",
        personal_access_token: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.username = username
        self.password = password
        self.personal_access_token = personal_access_token

        self._server_info: Optional[dict] = None
        self._is_server: Optional[bool] = None

    def _auth(self) -> Optional[str]:
        if self.personal_access_token:
            return "Bearer " + self.personal_access_token
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

    def _detect_server(self) -> None:
        """Call /rest/api/2/serverInfo once to determine deployment type."""
        if self._is_server is not None:
            return
        try:
            r = self._request("GET", "/rest/api/2/serverInfo")
            r.raise_for_status()
            self._server_info = r.json()
            deployment = self._server_info.get("deploymentType", "").lower()
            self._is_server = deployment == "server"
            version = self._server_info.get("version", "unknown")
            logger.info(
                "Jira detected: deploymentType=%s version=%s -> api=%s",
                deployment, version, self._api_version,
            )
        except Exception:
            logger.warning("Failed to detect Jira version, defaulting to Cloud (api/3)")
            self._is_server = False

    @property
    def _api_version(self) -> str:
        self._detect_server()
        return "2" if self._is_server else "3"

    def _api_path(self, path: str) -> str:
        return f"/rest/api/{self._api_version}{path}"

    def get_issue(self, key: str) -> dict:
        r = self._request("GET", self._api_path(f"/issue/{key}"))
        r.raise_for_status()
        return r.json()

    def add_comment(self, key: str, body: str) -> None:
        if self._is_server is None:
            self._detect_server()

        if self._is_server:
            payload: dict = {"body": body}
        else:
            payload = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}],
                }
            }

        r = self._request("POST", self._api_path(f"/issue/{key}/comment"), json=payload)
        r.raise_for_status()

    def transition(self, key: str, transition_name: str) -> None:
        r = self._request("GET", self._api_path(f"/issue/{key}/transitions"))
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
        r = self._request("POST", self._api_path(f"/issue/{key}/transitions"), json={"transition": {"id": tid}})
        r.raise_for_status()
