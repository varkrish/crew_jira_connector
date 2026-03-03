"""Pluggable Jira backends."""
from .base import JiraBackend
from .rest_backend import JiraRestBackend
from .atlassian_mcp import AtlassianMCPBackend
from .local_mcp import LocalMCPBackend

__all__ = ["JiraBackend", "JiraRestBackend", "AtlassianMCPBackend", "LocalMCPBackend"]
