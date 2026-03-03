"""
LLM-based classifier for Jira issues.
Determines mode (build/refactor/migration), extracts repo URLs, detects Gherkin.
"""
import json
import re
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class ClassificationResult:
    mode: str
    repo_url: Optional[str]
    has_gherkin: bool
    gherkin_features: list[str]
    confidence: float
    reasoning: str


PROMPT = """Classify this Jira issue into a development mode and extract metadata.

Modes:
- "build": Creating something new (new service, new app, new API, new component)
- "refactor": Modifying existing code (bug fix, feature addition, improvement, tech debt)
- "migration": Migrating between technology stacks (Java EE to Quarkus, monolith to microservices)

Also:
- Extract any repository URL (GitHub, GitLab, Bitbucket) from the text
- Detect if the text contains Gherkin scenarios (Given/When/Then)
- If Gherkin is found, extract each Feature block as a separate scenario

Issue:
{summary}

{description}

Respond as JSON only, no markdown:
{{
  "mode": "build|refactor|migration",
  "repo_url": "url or null",
  "has_gherkin": true|false,
  "gherkin_features": ["Feature: ...\\n  Scenario: ...\\n    Given...\\n    When...\\n    Then..."],
  "confidence": 0.0-1.0,
  "reasoning": "one line"
}}
"""

REPO_URL_PATTERN = re.compile(
    r"https?://(?:[^/]+\.)?(github\.com|gitlab\.com|bitbucket\.org)/[^\s\)\"']+",
    re.IGNORECASE,
)


def _fallback_mode(
    issue_type: Optional[str],
    mode_map: dict[str, str],
    has_repo_url: bool,
    default_mode: str,
) -> str:
    if issue_type and issue_type in mode_map:
        return mode_map[issue_type]
    if has_repo_url:
        return "refactor"
    return default_mode


def _extract_repo_from_text(text: str) -> Optional[str]:
    m = REPO_URL_PATTERN.search(text)
    return m.group(0) if m else None


async def classify_issue(
    summary: str,
    description: str,
    issue_type: Optional[str],
    api_base_url: str,
    api_key: str,
    model: str,
    mode_map: dict[str, str],
    default_mode: str,
    confidence_threshold: float,
) -> ClassificationResult:
    """
    Call LLM to classify the issue. On failure or low confidence, use fallback.
    """
    text = f"{summary}\n\n{description}"
    fallback_repo = _extract_repo_from_text(text)

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{api_base_url.rstrip('/')}/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": PROMPT.format(summary=summary or "(none)", description=description or "(none)")}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                },
                timeout=30.0,
            )
            r.raise_for_status()
            data = r.json()
            content = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    except Exception:
        return ClassificationResult(
            mode=_fallback_mode(issue_type, mode_map, bool(fallback_repo), default_mode),
            repo_url=fallback_repo,
            has_gherkin=False,
            gherkin_features=[],
            confidence=0.0,
            reasoning="LLM unavailable, used fallback",
        )

    # Parse JSON from response (handle markdown code blocks)
    if "```" in content:
        for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", content):
            try:
                data = json.loads(block.strip())
                break
            except json.JSONDecodeError:
                continue
        else:
            data = {}
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {}

    mode = (data.get("mode") or "").lower()
    if mode not in ("build", "refactor", "migration"):
        mode = _fallback_mode(issue_type, mode_map, bool(fallback_repo), default_mode)

    repo_url = data.get("repo_url") or fallback_repo
    if repo_url and isinstance(repo_url, str):
        repo_url = repo_url.strip()
    else:
        repo_url = fallback_repo

    has_gherkin = bool(data.get("has_gherkin"))
    gherkin_features = data.get("gherkin_features") or []
    if not isinstance(gherkin_features, list):
        gherkin_features = []

    confidence = float(data.get("confidence", 0))
    if confidence < confidence_threshold:
        mode = _fallback_mode(issue_type, mode_map, bool(repo_url), default_mode)

    return ClassificationResult(
        mode=mode,
        repo_url=repo_url,
        has_gherkin=has_gherkin,
        gherkin_features=gherkin_features,
        confidence=confidence,
        reasoning=str(data.get("reasoning", ""))[:200],
    )
