"""
Background poller that syncs Crew job status back to Jira (comments + transitions).
Supports per-story progress for Epic jobs.
"""
import json
import logging
import threading
import time
from typing import Any, Optional

from crew_jira_connector.config import get_settings
from crew_jira_connector.crew_client import CrewClient
from crew_jira_connector.db import IssueJobDB

logger = logging.getLogger(__name__)


class StatusPoller:
    def __init__(
        self,
        db: IssueJobDB,
        crew_client: CrewClient,
        jira_backend: Any,
        interval_seconds: int = 15,
    ):
        self.db = db
        self.crew_client = crew_client
        self.jira_backend = jira_backend
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Status poller started (interval=%ds)", self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval_seconds * 2)
            self._thread = None
        logger.info("Status poller stopped")

    def _messages_from_status(self, status: dict) -> list[dict]:
        raw = status.get("last_message") or status.get("messages") or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return []
        return raw if isinstance(raw, list) else []

    def _process_epic_story_events(self, issue_key: str, job_id: str, status: dict, settings) -> None:
        epic = self.db.get_epic(issue_key)
        if not epic:
            return

        for msg in self._messages_from_status(status):
            if msg.get("type") != "story_completed":
                continue
            story_key = msg.get("story_key")
            if not story_key:
                continue
            existing = self.db.get_story_progress(story_key)
            if existing and existing.get("status") == "done":
                continue

            commit_sha = msg.get("commit_sha", "")
            try:
                self.jira_backend.add_comment(
                    story_key,
                    f"Crew story completed (job {job_id}). Commit: {commit_sha[:7] if commit_sha else 'n/a'}",
                )
                self.jira_backend.transition(story_key, settings.jira_transition_done)
            except Exception as e:
                logger.warning("Failed to update Jira story %s: %s", story_key, e)

            self.db.update_story_progress(issue_key, story_key, "done", commit_sha=commit_sha)
            idx = msg.get("index")
            if idx is not None:
                self.db.advance_story_index(issue_key, int(idx) + 1)

    def _run_once(self) -> None:
        """Single poll iteration. Useful for testing."""
        settings = get_settings()
        transition_done = settings.jira_transition_done
        transition_failed = settings.jira_transition_failed

        active = self.db.list_active()
        for row in active:
            issue_key = row["issue_key"]
            job_id = row["job_id"]
            try:
                status = self.crew_client.get_job_status(job_id)
            except Exception as e:
                logger.warning("Failed to get job %s status: %s", job_id, e)
                continue

            self._process_epic_story_events(issue_key, job_id, status, settings)

            phase = status.get("current_phase") or status.get("phase") or ""
            job_status = status.get("status") or ""

            if job_status in ("completed", "done", "success"):
                try:
                    epic = self.db.get_epic(issue_key)
                    if epic:
                        self.jira_backend.add_comment(
                            issue_key,
                            f"Epic Crew job {job_id} completed. All stories processed.",
                        )
                    else:
                        self.jira_backend.add_comment(
                            issue_key,
                            f"Crew job {job_id} completed. Phase: {phase}",
                        )
                    self.jira_backend.transition(issue_key, transition_done)
                except Exception as e:
                    logger.warning("Failed to update Jira for %s: %s", issue_key, e)
                self.db.update_status(issue_key, "done")
            elif job_status in ("failed", "error"):
                try:
                    msg = status.get("message") or status.get("error") or "Job failed"
                    self.jira_backend.add_comment(
                        issue_key,
                        f"Crew job {job_id} failed: {msg}",
                    )
                    self.jira_backend.transition(issue_key, transition_failed)
                except Exception as e:
                    logger.warning("Failed to update Jira for %s: %s", issue_key, e)
                self.db.update_status(issue_key, "done")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._run_once()
            except Exception as e:
                logger.exception("Poller iteration error: %s", e)
            self._stop.wait(self.interval_seconds)
