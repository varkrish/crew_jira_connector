"""
FastAPI entry point for crew_jira_connector.
"""
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from crew_jira_connector.config import Settings, get_settings
from crew_jira_connector.crew_client import CrewClient
from crew_jira_connector.db import IssueJobDB
from crew_jira_connector.jira_backends import JiraRestBackend, AtlassianMCPBackend, LocalMCPBackend
from crew_jira_connector.jira_backends.base import JiraBackend
from crew_jira_connector.status_poller import StatusPoller
from crew_jira_connector.webhook_handler import process_webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_db: IssueJobDB | None = None
_poller: StatusPoller | None = None
_jira_backend: JiraBackend | None = None


def _create_jira_backend(settings: Settings) -> JiraBackend:
    """Factory: create the right backend based on JIRA_BACKEND config."""
    if settings.jira_backend == "atlassian_mcp":
        return AtlassianMCPBackend(
            api_token=settings.jira_api_token,
            email=settings.jira_email,
            cloud_id=settings.jira_cloud_id,
            mcp_endpoint=settings.atlassian_mcp_endpoint,
        )
    if settings.jira_backend == "local_mcp":
        return LocalMCPBackend(
            mcp_command=settings.local_mcp_command or None,
            mcp_http_url=settings.local_mcp_http_url or None,
            env={
                "JIRA_HOST": settings.jira_base_url,
                "JIRA_EMAIL": settings.jira_email,
                "JIRA_API_TOKEN": settings.jira_api_token,
            },
        )
    return JiraRestBackend(
        base_url=settings.jira_base_url,
        email=settings.jira_email,
        api_token=settings.jira_api_token,
        username=settings.jira_username,
        password=settings.jira_password,
        personal_access_token=settings.jira_personal_access_token,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db, _poller, _jira_backend
    settings = get_settings()
    _db = IssueJobDB(settings.db_path)
    _jira_backend = _create_jira_backend(settings)
    client = CrewClient(settings.crew_studio_url)
    _poller = StatusPoller(_db, client, _jira_backend, settings.poll_interval_seconds)
    _poller.start()
    yield
    if _poller:
        _poller.stop()
    if settings.jira_backend == "local_mcp" and hasattr(_jira_backend, "shutdown"):
        _jira_backend.shutdown()


app = FastAPI(title="Crew Jira Connector", version="0.1.0", lifespan=lifespan)


def _get_jira_backend() -> JiraBackend:
    if _jira_backend:
        return _jira_backend
    return _create_jira_backend(get_settings())


@app.post("/webhooks/jira")
async def jira_webhook(request: Request):
    """Handle Jira webhook for issue_created / issue_updated."""
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        logger.warning("Invalid webhook payload: %s", e)
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    signature = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Jira-Signature")
    backend = _get_jira_backend()
    db = _db or IssueJobDB(get_settings().db_path)

    status, body = await process_webhook(payload, raw, signature, backend, db)
    return JSONResponse(body, status_code=status)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"service": "crew-jira-connector", "version": "0.1.0"}
