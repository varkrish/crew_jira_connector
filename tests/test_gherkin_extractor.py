"""Unit tests for gherkin_extractor."""
from pathlib import Path

import pytest

from crew_jira_connector.gherkin_extractor import extract_feature_blocks, feature_to_filename, write_feature_files


SAMPLE_GHERKIN = """
Feature: User pagination
  As an API consumer
  I want to paginate user listings

  Scenario: Default page size
    Given there are 100 users
    When I request GET /api/users
    Then I should receive 20 users
"""


def test_extract_feature_blocks():
    blocks = extract_feature_blocks(SAMPLE_GHERKIN)
    assert len(blocks) >= 1
    assert "Feature:" in blocks[0]
    assert "Scenario:" in blocks[0]


def test_extract_feature_blocks_empty():
    assert extract_feature_blocks("") == []
    assert extract_feature_blocks("No gherkin here") == []


def test_feature_to_filename():
    name = feature_to_filename(SAMPLE_GHERKIN, 0)
    assert name.endswith(".feature")
    assert "User_pagination" in name or "feature_0" in name


def test_write_feature_files(tmp_path):
    blocks = extract_feature_blocks(SAMPLE_GHERKIN)
    paths = write_feature_files(blocks, tmp_path)
    assert len(paths) >= 1
    assert paths[0].exists()
    assert paths[0].read_text().startswith("Feature:")
