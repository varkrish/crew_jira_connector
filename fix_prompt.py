"""Structured prompts for JIRA bug / fix jobs (connector copy)."""


def build_fix_vision(
    *,
    summary: str,
    description: str = "",
    issue_key: str = "",
    expected: str = "",
    actual: str = "",
) -> str:
    key_line = f"Fix JIRA {issue_key}: {summary}" if issue_key else f"Fix: {summary}"
    parts = [key_line, ""]
    if description.strip():
        parts.extend(["Steps to reproduce / description:", description.strip(), ""])
    if expected.strip():
        parts.extend(["Expected:", expected.strip(), ""])
    if actual.strip():
        parts.extend(["Actual:", actual.strip(), ""])
    parts.extend([
        "Constraints:",
        "- Minimal, targeted change; do not refactor unrelated code",
        "- Preserve existing patterns in tech_stack.md and project conventions",
        "- Update or add tests that cover the fix",
    ])
    return "\n".join(parts)
