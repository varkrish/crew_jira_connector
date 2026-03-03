"""
Configuration for crew_jira_connector.
Loads from environment variables; supports shared ~/.crew-ai/config.yaml for LLM.
"""
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Crew Studio
    crew_studio_url: str = "http://localhost:8081"

    # Jira backend
    jira_backend: str = "rest"
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_username: str = ""
    jira_password: str = ""

    # Webhook filtering
    jira_project_keys: str = ""
    jira_trigger_status: str = "Ready for Dev"
    jira_webhook_secret: str = ""

    # Validation
    max_vision_length: int = 50_000
    allowed_git_hosts: str = "github.com,gitlab.com,bitbucket.org"
    validate_repo_access: bool = True
    min_summary_length: int = 10

    # AI classifier (uses same LLM as Crew Studio)
    classifier_confidence_threshold: float = 0.5
    jira_mode_map: str = ""
    jira_default_mode: str = "build"

    # LLM (shared with Crew Studio config or env)
    llm_api_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Status sync
    jira_transition_done: str = "Done"
    jira_transition_failed: str = "Failed"
    poll_interval_seconds: int = 15

    # MCP backends
    local_mcp_command: str = ""
    local_mcp_http_url: str = ""
    atlassian_mcp_endpoint: str = "https://mcp.atlassian.com/v1/mcp"
    jira_cloud_id: str = ""

    # Data
    db_path: str = "./data/connector.db"

    @property
    def jira_project_keys_list(self) -> list[str]:
        if not self.jira_project_keys:
            return []
        return [k.strip() for k in self.jira_project_keys.split(",") if k.strip()]

    @property
    def allowed_git_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_git_hosts.split(",") if h.strip()]

    @property
    def jira_mode_map_dict(self) -> dict[str, str]:
        if not self.jira_mode_map:
            return {}
        result = {}
        for pair in self.jira_mode_map.split(","):
            parts = pair.strip().split("=")
            if len(parts) == 2:
                result[parts[0].strip()] = parts[1].strip()
        return result


def load_llm_config_from_crew_ai() -> tuple[str, str, str]:
    """Load LLM config from ~/.crew-ai/config.yaml if env vars not set."""
    import yaml

    base = os.environ.get("LLM_API_BASE_URL") or ""
    key = os.environ.get("LLM_API_KEY") or ""
    model = os.environ.get("LLM_MODEL") or "gpt-4o-mini"

    if base and key:
        return base, key, model

    config_paths = [
        Path.home() / ".crew-ai" / "config.yaml",
        Path("config.yaml"),
        Path("/etc/crew-ai/config.yaml"),
    ]
    for p in config_paths:
        if p.exists():
            try:
                with open(p) as f:
                    cfg = yaml.safe_load(f)
                if cfg and "llm" in cfg:
                    llm = cfg["llm"]
                    base = base or llm.get("api_base_url", "")
                    key = key or llm.get("api_key", "")
                    model = model or llm.get("model_worker", llm.get("model_manager", "gpt-4o-mini"))
                if base and key:
                    return base, key, model
            except Exception:
                pass
    return base, key, model


def get_settings() -> Settings:
    s = Settings()
    if not s.llm_api_base_url or not s.llm_api_key:
        base, key, model = load_llm_config_from_crew_ai()
        s.llm_api_base_url = s.llm_api_base_url or base
        s.llm_api_key = s.llm_api_key or key
        s.llm_model = s.llm_model or model
    return s
