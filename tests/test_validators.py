"""Unit tests for validators."""
import pytest

from crew_jira_connector.validators import (
    check_repo_access,
    validate_classifier_output,
    validate_content,
    validate_and_extract_repo_urls,
    verify_webhook_signature,
)


def test_verify_webhook_signature_no_secret():
    assert verify_webhook_signature(b"{}", None, "") is True
    assert verify_webhook_signature(b"{}", "sha256=abc", "") is True


def test_verify_webhook_signature_with_secret():
    import hmac
    import hashlib
    payload = b'{"issue":{"key":"X-1"}}'
    secret = "my-secret"
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(payload, sig, secret) is True
    assert verify_webhook_signature(payload, "sha256=wrong", secret) is False
    assert verify_webhook_signature(payload, None, secret) is False


def test_validate_content_ok():
    ok, errs, vision = validate_content("Add pagination to users API", "As a user I want...")
    assert ok is True
    assert len(errs) == 0
    assert "pagination" in vision


def test_validate_content_short_summary():
    ok, errs, _ = validate_content("Fix", "Some description", min_summary_length=10)
    assert ok is False
    assert any("10" in e for e in errs)


def test_validate_content_tbd():
    ok, errs, _ = validate_content("TBD", "TBD")
    assert ok is False


def test_validate_content_max_length():
    ok, errs, _ = validate_content("A" * 20, "B" * 50_100, max_length=50_000)
    assert ok is False


def test_validate_and_extract_repo_urls():
    text = "See https://github.com/acme/backend for the repo."
    ok, urls, errs = validate_and_extract_repo_urls(text, ["github.com", "gitlab.com", "bitbucket.org"])
    assert ok is True
    assert "https://github.com/acme/backend" in urls
    assert len(errs) == 0


def test_validate_and_extract_repo_urls_disallowed_host():
    text = "See https://github.com/acme/backend and https://gitlab.com/other/repo"
    ok, urls, errs = validate_and_extract_repo_urls(text, ["github.com"])
    assert ok is False
    assert len(errs) >= 1


def test_validate_classifier_output_ok():
    ok, errs = validate_classifier_output(
        mode="refactor",
        repo_url="https://github.com/a/b",
        has_gherkin=False,
        gherkin_features=[],
        confidence=0.9,
        threshold=0.5,
    )
    assert ok is True
    assert len(errs) == 0


def test_validate_classifier_output_refactor_no_repo():
    ok, errs = validate_classifier_output(
        mode="refactor",
        repo_url=None,
        has_gherkin=False,
        gherkin_features=[],
        confidence=0.9,
        threshold=0.5,
    )
    assert ok is False
    assert any("repository" in e.lower() for e in errs)


def test_validate_classifier_output_low_confidence():
    ok, errs = validate_classifier_output(
        mode="build",
        repo_url=None,
        has_gherkin=False,
        gherkin_features=[],
        confidence=0.3,
        threshold=0.5,
    )
    assert ok is False
