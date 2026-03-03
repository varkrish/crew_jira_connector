"""Unit tests for db."""
import pytest

from crew_jira_connector.db import IssueJobDB


def test_insert_and_get(db):
    db.insert("PROJ-1", "job-abc", "refactor")
    row = db.get_by_issue("PROJ-1")
    assert row is not None
    assert row["job_id"] == "job-abc"
    assert row["mode"] == "refactor"
    assert row["status"] == "active"


def test_has_active_job(db):
    assert db.has_active_job("PROJ-1") is False
    db.insert("PROJ-1", "job-abc", "build")
    assert db.has_active_job("PROJ-1") is True
    db.update_status("PROJ-1", "done")
    assert db.has_active_job("PROJ-1") is False


def test_list_active(db):
    db.insert("P-1", "j1", "build")
    db.insert("P-2", "j2", "refactor")
    db.update_status("P-1", "done")
    active = db.list_active()
    assert len(active) == 1
    assert active[0]["issue_key"] == "P-2"
