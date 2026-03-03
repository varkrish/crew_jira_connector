"""Pytest fixtures for crew_jira_connector tests."""
import tempfile
from pathlib import Path

import pytest

from crew_jira_connector.db import IssueJobDB


@pytest.fixture
def temp_db():
    """Provide a temporary SQLite database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def db(temp_db):
    """Provide an IssueJobDB instance with temp storage."""
    return IssueJobDB(temp_db)


@pytest.fixture
def mock_jira_webhook_payload():
    """Standard Jira webhook payload for testing."""
    return {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "PROJ-42",
            "fields": {
                "summary": "Add pagination to user API",
                "description": "Implement paginated GET /api/users with page and page_size query parameters. See https://github.com/acme/backend for the repo.",
                "issuetype": {"name": "Story"},
                "status": {"name": "Ready for Dev"},
                "project": {"key": "PROJ"},
            },
        },
    }
