"""
Background poller that syncs Crew job status back to Jira (comments + transitions).
"""
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

            phase = status.get("current_phase") or status.get("phase") or ""
            job_status = status.get("status") or ""

            if job_status in ("completed", "done", "success"):
                try:
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
