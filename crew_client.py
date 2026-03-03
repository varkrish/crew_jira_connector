"""
Crew Studio REST API client.
Handles two-step flow for refactor/migration and multipart uploads for .feature files.
"""
import tempfile
from pathlib import Path
from typing import Optional

import httpx


class CrewClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def create_job(
        self,
        vision: str,
        github_urls: Optional[list[str]] = None,
        mode: str = "build",
        feature_files: Optional[list[Path]] = None,
    ) -> dict:
        """
        Create a job via POST /api/jobs.
        For build: pipeline starts automatically.
        For refactor/migration: returns job_id, caller must call trigger_refactor/trigger_migration.
        """
        github_urls = github_urls or []
        files = list(feature_files) if feature_files else []

        if files:
            data: list[tuple[str, str | tuple[str, bytes, str]]] = [
                ("vision", vision),
                ("mode", mode),
            ]
            for u in github_urls:
                data.append(("github_urls", u))
            file_tuples = [
                ("documents", (p.name, p.read_bytes(), "text/plain"))
                for p in files
                if p.exists()
            ]
            r = httpx.post(
                f"{self.base_url}/api/jobs",
                data=data,
                files=file_tuples,
                timeout=120.0,
            )
        else:
            r = httpx.post(
                f"{self.base_url}/api/jobs",
                json={
                    "vision": vision,
                    "github_urls": github_urls,
                    "mode": mode,
                },
                timeout=120.0,
            )

        r.raise_for_status()
        return r.json()

    def trigger_refactor(
        self,
        job_id: str,
        target_stack: str = "Java 17",
        instructions: str = "",
        tech_preferences: str = "",
    ) -> dict:
        """Trigger refactor runner. Call after create_job with mode=refactor."""
        r = httpx.post(
            f"{self.base_url}/api/jobs/{job_id}/refactor",
            json={
                "target_stack": target_stack,
                "devops_instructions": instructions,
                "tech_preferences": tech_preferences,
            },
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()

    def trigger_migration(
        self,
        job_id: str,
        migration_goal: str = "",
        migration_notes: Optional[str] = None,
    ) -> dict:
        """Trigger migration runner. Call after create_job with mode=migration. Requires MTA report in job."""
        r = httpx.post(
            f"{self.base_url}/api/jobs/{job_id}/migrate",
            json={
                "migration_goal": migration_goal or "Analyse the MTA report and apply all migration changes",
                "migration_notes": migration_notes,
            },
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()

    def get_job_status(self, job_id: str) -> dict:
        """Get job status via GET /api/jobs/<id>."""
        r = httpx.get(f"{self.base_url}/api/jobs/{job_id}", timeout=30.0)
        r.raise_for_status()
        return r.json()
