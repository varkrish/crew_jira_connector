"""Epic story planning — fetch and format Jira Epic child stories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class StorySpec:
    key: str
    summary: str
    description: str
    status: str
    order: int

    def to_metadata_dict(self) -> dict:
        return {
            "key": self.key,
            "summary": self.summary,
            "description": self.description,
            "status": self.status,
            "order": self.order,
        }


def _extract_description(fields: dict) -> str:
    desc = fields.get("description")
    if desc is None:
        return ""
    if isinstance(desc, dict):
        def _text(obj: Any) -> str:
            if isinstance(obj, dict):
                if obj.get("type") == "text":
                    return obj.get("text", "")
                return " ".join(_text(c) for c in obj.get("content", []))
            if isinstance(obj, list):
                return " ".join(_text(x) for x in obj)
            return str(obj)

        return _text(desc).strip()
    return str(desc).strip()


def get_epic_stories(jira_backend: Any, epic_key: str, jql_template: Optional[str] = None) -> list[StorySpec]:
    template = jql_template or '"Epic Link" = {epic_key} ORDER BY created ASC'
    jql = template.format(epic_key=epic_key)
    issues = jira_backend.search(jql)
    if not issues:
        raise ValueError(f"Epic {epic_key} has no stories linked")

    stories: list[StorySpec] = []
    for idx, issue in enumerate(issues):
        fields = issue.get("fields") or {}
        status_obj = fields.get("status") or {}
        stories.append(
            StorySpec(
                key=issue.get("key", ""),
                summary=(fields.get("summary") or "").strip(),
                description=_extract_description(fields),
                status=status_obj.get("name", ""),
                order=idx,
            )
        )
    return stories


def build_epic_vision(epic_summary: str, epic_description: str, stories: list[StorySpec]) -> str:
    lines = [
        f"# Epic: {epic_summary}",
        epic_description,
        "",
        "## User Stories (implement in order)",
    ]
    for s in stories:
        lines.append(f"- [{s.key}] {s.summary}: {s.description[:500]}")
    return "\n".join(lines).strip()
