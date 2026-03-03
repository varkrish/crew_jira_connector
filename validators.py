"""
Input validation pipeline for Jira webhook payloads.
Runs before creating any Crew job. All checks must pass or webhook is rejected.
"""
import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import httpx


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sanitized_vision: str = ""
    repo_urls: list[str] = field(default_factory=list)
    issue_key: str = ""
    project_key: str = ""


# Patterns that indicate non-actionable content
NON_ACTIONABLE = re.compile(
    r"^(TBD|WIP|TODO|N\/A|N\/A\.|\.\.\.|\s*)$",
    re.IGNORECASE | re.MULTILINE,
)
# Git URL patterns
GIT_URL_PATTERN = re.compile(
    r"https?://(?:[^/]+\.)?(github\.com|gitlab\.com|bitbucket\.org)/([^/\s]+)/([^/\s#?]+)(?:\.git)?(?:\s|$|[#?])",
    re.IGNORECASE,
)
# Blocked for SSRF
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
BLOCKED_NETWORKS = ("10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.", "192.168.")


def verify_webhook_signature(payload: bytes, signature_header: Optional[str], secret: str) -> bool:
    """Verify HMAC signature if JIRA_WEBHOOK_SECRET is set."""
    if not secret:
        return True
    if not signature_header:
        return False
    # Common formats: X-Hub-Signature-256: sha256=..., or X-Jira-Signature: ...
    sig = signature_header.strip()
    if sig.startswith("sha256="):
        sig = sig[7:]
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def validate_content(
    summary: str,
    description: str,
    max_length: int = 50_000,
    min_summary_length: int = 10,
) -> tuple[bool, list[str], str]:
    """
    Validate summary and description. Returns (valid, errors, sanitized_vision).
    """
    errors: list[str] = []
    summary = (summary or "").strip()
    description = (description or "").strip()
    combined = f"{summary}\n\n{description}".strip()

    if len(summary) < min_summary_length:
        errors.append(f"Summary must be at least {min_summary_length} characters.")

    if not description and len(summary) < 30:
        errors.append("Description is empty and summary is too short. Please add details.")

    if combined and NON_ACTIONABLE.match(combined):
        errors.append("Content appears non-actionable (e.g. TBD, WIP). Please add details.")

    if len(combined) > max_length:
        errors.append(f"Content exceeds maximum length of {max_length} characters.")

    if errors:
        return False, errors, combined

    return True, [], combined


def _is_blocked_host(host: str) -> bool:
    host_lower = host.lower()
    if host_lower in BLOCKED_HOSTS:
        return True
    if host_lower.startswith("169.254."):
        return True
    if any(host.startswith(p) for p in BLOCKED_NETWORKS):
        return True
    return False


def validate_and_extract_repo_urls(
    text: str,
    allowed_hosts: list[str],
) -> tuple[bool, list[str], list[str]]:
    """
    Extract and validate repo URLs from text. Returns (valid, repo_urls, errors).
    SSRF: blocks localhost, private IPs, non-git hosts.
    """
    errors: list[str] = []
    seen: set[str] = set()
    repo_urls: list[str] = []

    for m in GIT_URL_PATTERN.finditer(text):
        host = m.group(1).lower()
        owner = m.group(2)
        repo = m.group(3)
        raw_url = f"https://{host}/{owner}/{repo}"

        if host not in [h.lower() for h in allowed_hosts]:
            errors.append(f"Repository host '{host}' is not in allowed list: {allowed_hosts}")
            continue

        parsed = urlparse(raw_url)
        if _is_blocked_host(parsed.hostname or ""):
            errors.append(f"Blocked URL (SSRF): {raw_url}")
            continue

        # Reject non-repo paths
        path = (parsed.path or "").strip("/")
        if path in ("settings", "notifications", "explore", "topics", "organizations"):
            continue

        norm = raw_url.rstrip("/")
        if norm not in seen:
            seen.add(norm)
            repo_urls.append(norm)

    return len(errors) == 0, repo_urls, errors


def check_repo_access(url: str, timeout: float = 5.0) -> tuple[bool, Optional[str]]:
    """
    Lightweight HEAD check for GitHub/GitLab/Bitbucket.
    Returns (accessible, error_message).
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").strip("/")
    if "/" not in path:
        return False, "Invalid repo path"

    owner, repo = path.split("/", 1)
    if host == "github.com":
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
    elif host == "gitlab.com":
        api_url = f"https://gitlab.com/api/v4/projects/{owner}%2F{repo}"
    elif host == "bitbucket.org":
        api_url = f"https://api.bitbucket.org/2.0/repositories/{owner}/{repo}"
    else:
        return True, None  # Skip check for unknown hosts

    try:
        r = httpx.head(api_url, timeout=timeout)
        if r.status_code in (200, 204):
            return True, None
        if r.status_code == 404:
            return False, f"Repository not found: {url}"
        return False, f"Repository returned status {r.status_code}"
    except httpx.TimeoutException:
        return True, None  # Proceed on timeout
    except Exception as e:
        return False, str(e)


def validate_classifier_output(
    mode: str,
    repo_url: Optional[str],
    has_gherkin: bool,
    gherkin_features: list[str],
    confidence: float,
    threshold: float,
) -> tuple[bool, list[str]]:
    """
    Validate AI classifier output. Returns (valid, errors).
    """
    errors: list[str] = []
    valid_modes = {"build", "refactor", "migration"}

    if mode not in valid_modes:
        errors.append(f"Invalid mode '{mode}'. Must be one of: {', '.join(valid_modes)}")

    if mode in ("refactor", "migration") and not repo_url:
        errors.append("Refactor and migration modes require a repository URL.")

    if confidence < threshold:
        errors.append(f"Classification confidence ({confidence:.2f}) is below threshold ({threshold}).")

    if has_gherkin and gherkin_features:
        for i, feat in enumerate(gherkin_features):
            if "Feature:" not in feat:
                errors.append(f"Gherkin feature {i + 1} missing 'Feature:' keyword.")
            elif "Scenario:" not in feat and "Scenario Outline:" not in feat:
                errors.append(f"Gherkin feature {i + 1} has no Scenario.")

    return len(errors) == 0, errors
