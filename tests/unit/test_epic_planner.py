"""TDD tests for epic story fetching."""

from unittest.mock import MagicMock, patch

import pytest

from crew_jira_connector.epic_planner import StorySpec, build_epic_vision, get_epic_stories


@pytest.fixture
def mock_backend():
    return MagicMock()


def test_get_epic_stories_from_jql(mock_backend):
    mock_backend.search.return_value = [
        {
            "key": "PROJ-101",
            "fields": {
                "summary": "User login",
                "description": "As a user I can log in",
                "status": {"name": "To Do"},
            },
        },
        {
            "key": "PROJ-102",
            "fields": {
                "summary": "User logout",
                "description": "As a user I can log out",
                "status": {"name": "To Do"},
            },
        },
    ]

    stories = get_epic_stories(mock_backend, "PROJ-100")
    assert len(stories) == 2
    assert stories[0].key == "PROJ-101"
    assert stories[0].summary == "User login"
    assert stories[0].order == 0
    assert stories[1].order == 1


def test_get_epic_stories_empty_raises(mock_backend):
    mock_backend.search.return_value = []
    with pytest.raises(ValueError, match="no stories"):
        get_epic_stories(mock_backend, "PROJ-100")


def test_build_epic_vision():
    stories = [
        StorySpec(key="P-1", summary="Login", description="desc1", status="To Do", order=0),
        StorySpec(key="P-2", summary="Logout", description="desc2", status="To Do", order=1),
    ]
    vision = build_epic_vision("Auth Epic", "Implement auth", stories)
    assert "Auth Epic" in vision
    assert "P-1" in vision
    assert "Login" in vision
    assert "P-2" in vision


def test_story_spec_to_metadata_dict():
    s = StorySpec(key="P-1", summary="S", description="D", status="To Do", order=0)
    d = s.to_metadata_dict()
    assert d == {"key": "P-1", "summary": "S", "description": "D", "status": "To Do", "order": 0}
