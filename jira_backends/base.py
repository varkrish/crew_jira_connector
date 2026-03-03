"""Abstract Jira backend interface."""
from abc import ABC, abstractmethod


class JiraBackend(ABC):
    @abstractmethod
    def get_issue(self, key: str) -> dict:
        """Fetch issue by key."""
        ...

    @abstractmethod
    def add_comment(self, key: str, body: str) -> None:
        """Add comment to issue."""
        ...

    @abstractmethod
    def transition(self, key: str, transition_name: str) -> None:
        """Transition issue to status."""
        ...

    def search(self, jql: str) -> list[dict]:
        """Search issues by JQL. Optional, default returns empty list."""
        return []
