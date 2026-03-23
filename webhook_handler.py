"""
Jira webhook handler: validation pipeline, AI classifier, job creation, DB storage.
"""
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from crew_jira_connector.ai_classifier import classify_issue
from crew_jira_connector.config import get_settings
from crew_jira_connector.crew_client import CrewClient
from crew_jira_connector.db import IssueJobDB
from crew_jira_connector.gherkin_extractor import extract_feature_blocks, write_feature_files
from crew_jira_connector.validators import (
    ValidationResult,
    check_repo_access,
    validate_classifier_output,
    validate_content,
    validate_and_extract_repo_urls,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)


def _get_issue_key(payload: dict) -> Optional[str]:
    issue = payload.get("issue") or {}
    return issue.get("key")


def _get_project_key(payload: dict) -> Optional[str]:
    issue = payload.get("issue") or {}
    proj = issue.get("fields", {}).get("project") or {}
    return proj.get("key")


def _get_status_name(payload: dict) -> Optional[str]:
    issue = payload.get("issue") or {}
    status = issue.get("fields", {}).get("status") or {}
    return status.get("name")


def _get_issue_type(payload: dict) -> Optional[str]:
    issue = payload.get("issue") or {}
    it = issue.get("fields", {}).get("issuetype") or {}
    return it.get("name")


def _get_summary(payload: dict) -> str:
    issue = payload.get("issue") or {}
    return (issue.get("fields", {}).get("summary") or "").strip()


def _get_description(payload: dict) -> str:
    issue = payload.get("issue") or {}
    desc = issue.get("fields", {}).get("description")
    if desc is None:
        return ""
    if isinstance(desc, dict):
        # ADF format - extract plain text
        def _extract_text(obj: Any) -> str:
            if isinstance(obj, dict):
                if obj.get("type") == "text":
                    return obj.get("text", "")
                content = obj.get("content", [])
                return " ".join(_extract_text(c) for c in content)
            if isinstance(obj, list):
                return " ".join(_extract_text(x) for x in obj)
            return str(obj)

        return _extract_text(desc).strip()
    return str(desc).strip()


async def process_webhook(
    payload: dict,
    raw_body: bytes,
    signature_header: Optional[str],
    jira_backend: Any,
    db: IssueJobDB,
) -> tuple[int, dict]:
    """
    Process Jira webhook. Returns (status_code, response_dict).
    """
    settings = get_settings()

    # 1. Webhook auth
    if settings.jira_webhook_secret:
        if not verify_webhook_signature(raw_body, signature_header, settings.jira_webhook_secret):
            return 401, {"error": "Invalid webhook signature"}

    # 2. Project + status filter
    project_key = _get_project_key(payload)
    status_name = _get_status_name(payload)
    if settings.jira_project_keys_list and project_key not in settings.jira_project_keys_list:
        return 200, {"skipped": "project not in filter"}
    if status_name != settings.jira_trigger_status:
        return 200, {"skipped": "status does not match trigger"}

    issue_key = _get_issue_key(payload)
    if not issue_key:
        return 400, {"error": "No issue key in payload"}

    # 3. Idempotency
    if db.has_active_job(issue_key):
        try:
            jira_backend.add_comment(issue_key, "A Crew job is already running for this issue.")
        except Exception as e:
            logger.warning("Failed to post idempotency comment: %s", e)
        return 200, {"skipped": "duplicate issue"}

    summary = _get_summary(payload)
    description = _get_description(payload)

    # 4. Content validation
    ok, errs, sanitized_vision = validate_content(
        summary, description,
        max_length=settings.max_vision_length,
        min_summary_length=settings.min_summary_length,
    )
    if not ok:
        _post_comment(jira_backend, issue_key, "Cannot start Crew job: " + "; ".join(errs))
        return 200, {"error": "content validation failed", "details": errs}

    # 5. URL validation (pre-classifier, on raw text)
    ok_url, repo_urls, url_errs = validate_and_extract_repo_urls(
        sanitized_vision, settings.allowed_git_hosts_list
    )
    if not ok_url and url_errs:
        _post_comment(jira_backend, issue_key, "Invalid repository URL: " + "; ".join(url_errs))
        return 200, {"error": "URL validation failed", "details": url_errs}

    # 6. Repo accessibility (optional)
    if settings.validate_repo_access and repo_urls:
        for url in repo_urls:
            acc, msg = check_repo_access(url)
            if not acc and msg:
                _post_comment(jira_backend, issue_key, f"Repository not accessible: {msg}")
                return 200, {"error": "repo access failed", "details": [msg]}

    # 7. AI classifier
    classification = await classify_issue(
        summary=summary,
        description=description,
        issue_type=_get_issue_type(payload),
        api_base_url=settings.llm_api_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        mode_map=settings.jira_mode_map_dict,
        default_mode=settings.jira_default_mode,
        confidence_threshold=settings.classifier_confidence_threshold,
    )

    # 8. Classifier output validation
    final_repo = classification.repo_url or (repo_urls[0] if repo_urls else None)
    ok_cls, cls_errs = validate_classifier_output(
        mode=classification.mode,
        repo_url=final_repo,
        has_gherkin=classification.has_gherkin,
        gherkin_features=classification.gherkin_features,
        confidence=classification.confidence,
        threshold=settings.classifier_confidence_threshold,
    )
    if not ok_cls:
        _post_comment(jira_backend, issue_key, "Could not classify issue: " + "; ".join(cls_errs))
        return 200, {"error": "classifier validation failed", "details": cls_errs}

    github_urls = [final_repo] if final_repo else []
    if not github_urls and repo_urls:
        github_urls = repo_urls

    # Gherkin: use classifier output or extract from text
    feature_blocks = classification.gherkin_features
    if not feature_blocks and classification.has_gherkin:
        feature_blocks = extract_feature_blocks(description)

    jira_metadata = {
        "jira_issue_key": issue_key,
        "jira_base_url": settings.jira_base_url,
        "jira_issue_url": f"{settings.jira_base_url}/browse/{issue_key}",
    }

    feature_files: list[Path] = []
    if feature_blocks:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            feature_files = write_feature_files(feature_blocks, tmp_path)
            client = CrewClient(settings.crew_studio_url)
            try:
                resp = client.create_job(
                    vision=sanitized_vision,
                    github_urls=github_urls,
                    mode=classification.mode,
                    feature_files=feature_files,
                    metadata=jira_metadata,
                )
            except Exception as e:
                logger.exception("Failed to create Crew job")
                _post_comment(jira_backend, issue_key, f"Failed to create Crew job: {e}")
                return 200, {"error": str(e)}

            job_id = resp.get("job_id")
            if not job_id:
                _post_comment(jira_backend, issue_key, "Crew Studio did not return job_id")
                return 200, {"error": "no job_id"}

            db.insert(issue_key, job_id, classification.mode)

            # Two-step: trigger refactor/migration
            if classification.mode == "refactor":
                try:
                    client.trigger_refactor(job_id, instructions=description)
                except Exception as e:
                    logger.warning("Failed to trigger refactor: %s", e)
                    _post_comment(jira_backend, issue_key, f"Job created but refactor trigger failed: {e}")
            elif classification.mode == "migration":
                try:
                    client.trigger_migration(job_id, migration_goal=description[:500])
                except Exception as e:
                    logger.warning("Failed to trigger migration: %s", e)
                    _post_comment(jira_backend, issue_key, f"Job created but migration trigger failed. Ensure MTA report is uploaded: {e}")

            _post_comment(jira_backend, issue_key, f"Crew job created: {job_id} (mode={classification.mode})")
            return 200, {"job_id": job_id, "issue_key": issue_key, "mode": classification.mode}
    else:
        client = CrewClient(settings.crew_studio_url)
        try:
            resp = client.create_job(
                vision=sanitized_vision,
                github_urls=github_urls,
                mode=classification.mode,
                feature_files=None,
                metadata=jira_metadata,
            )
        except Exception as e:
            logger.exception("Failed to create Crew job")
            _post_comment(jira_backend, issue_key, f"Failed to create Crew job: {e}")
            return 200, {"error": str(e)}

        job_id = resp.get("job_id")
        if not job_id:
            _post_comment(jira_backend, issue_key, "Crew Studio did not return job_id")
            return 200, {"error": "no job_id"}

        db.insert(issue_key, job_id, classification.mode)

        if classification.mode == "refactor":
            try:
                client.trigger_refactor(job_id, instructions=description)
            except Exception as e:
                logger.warning("Failed to trigger refactor: %s", e)
                _post_comment(jira_backend, issue_key, f"Job created but refactor trigger failed: {e}")
        elif classification.mode == "migration":
            try:
                client.trigger_migration(job_id, migration_goal=description[:500])
            except Exception as e:
                logger.warning("Failed to trigger migration: %s", e)
                _post_comment(jira_backend, issue_key, f"Job created but migration trigger failed. Ensure MTA report is uploaded: {e}")

        _post_comment(jira_backend, issue_key, f"Crew job created: {job_id} (mode={classification.mode})")
        return 200, {"job_id": job_id, "issue_key": issue_key, "mode": classification.mode}


def _post_comment(backend: Any, issue_key: str, body: str) -> None:
    try:
        backend.add_comment(issue_key, body)
    except Exception as e:
        logger.warning("Failed to post Jira comment: %s", e)
