"""Unit tests for AI classifier."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from crew_jira_connector.ai_classifier import (
    ClassificationResult,
    _extract_repo_from_text,
    _fallback_mode,
    classify_issue,
)


def test_extract_repo_from_text():
    text = "Fix bug in https://github.com/acme/backend please"
    url = _extract_repo_from_text(text)
    assert url is not None
    assert "github.com/acme/backend" in url


def test_extract_repo_from_text_none():
    assert _extract_repo_from_text("No URLs here") is None


def test_fallback_mode_issue_type():
    mode = _fallback_mode("Bug", {"Bug": "refactor"}, False, "build")
    assert mode == "refactor"


def test_fallback_mode_has_repo():
    mode = _fallback_mode(None, {}, True, "build")
    assert mode == "refactor"


def test_fallback_mode_default():
    mode = _fallback_mode(None, {}, False, "build")
    assert mode == "build"


@pytest.mark.asyncio
async def test_classify_issue_llm_failure():
    """When LLM is unavailable, fallback should be used."""
    result = await classify_issue(
        summary="Fix login bug",
        description="See https://github.com/acme/auth-service for the repo.",
        issue_type="Bug",
        api_base_url="http://unreachable:9999",
        api_key="fake",
        model="gpt-4o-mini",
        mode_map={"Bug": "refactor"},
        default_mode="build",
        confidence_threshold=0.5,
    )
    assert result.mode == "refactor"
    assert result.confidence == 0.0
    assert "fallback" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_classify_issue_success():
    """Test successful LLM classification with mocked response."""
    import httpx as real_httpx

    llm_json = json.dumps({
        "mode": "build",
        "repo_url": None,
        "has_gherkin": False,
        "gherkin_features": [],
        "confidence": 0.95,
        "reasoning": "New service creation",
    })
    llm_response_body = {"choices": [{"message": {"content": llm_json}}]}

    mock_response = MagicMock(spec=real_httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = llm_response_body
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    async_cm = AsyncMock()
    async_cm.__aenter__ = AsyncMock(return_value=mock_client)
    async_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("crew_jira_connector.ai_classifier.httpx.AsyncClient", return_value=async_cm):
        result = await classify_issue(
            summary="Create a payment microservice",
            description="We need a new service to handle Stripe payments",
            issue_type="Story",
            api_base_url="http://localhost:1234",
            api_key="test-key",
            model="gpt-4o-mini",
            mode_map={},
            default_mode="build",
            confidence_threshold=0.5,
        )
        assert result.mode == "build"
        assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_classify_issue_low_confidence():
    """Low confidence should trigger fallback."""
    llm_response = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "mode": "migration",
                    "repo_url": None,
                    "has_gherkin": False,
                    "gherkin_features": [],
                    "confidence": 0.2,
                    "reasoning": "Unclear",
                })
            }
        }]
    }

    with patch("crew_jira_connector.ai_classifier.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.json.return_value = llm_response
        mock_resp.raise_for_status = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await classify_issue(
            summary="Update the system",
            description="Make it better",
            issue_type=None,
            api_base_url="http://localhost:1234",
            api_key="test-key",
            model="gpt-4o-mini",
            mode_map={},
            default_mode="build",
            confidence_threshold=0.5,
        )
        assert result.mode == "build"
