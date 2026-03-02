"""Base types for reporoot integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class IntegrationContext:
    """Data passed to integration hooks."""

    root: Path
    """Workspace root directory."""

    project: str
    """Active project name (may be multi-segment, e.g., 'chatly/web-app')."""

    repos: dict[str, dict]
    """Repo entries from the project's .repos file: {local_path: {type, url, version, role, ...}}."""

    config: dict
    """Per-integration config from the 'integrations' key in the .repos file."""

    all_repos_on_disk: set[str] = field(default_factory=set)
    """All git repos found on disk under registry directories (relative paths).
    Populated once by the registry, shared across integrations."""

    all_project_paths: list[str] = field(default_factory=list)
    """All project paths (e.g., ['web-app', 'mobile-app']).
    Populated once by the registry, shared across integrations."""


@dataclass
class Issue:
    """A problem found by an integration's check hook."""

    integration: str
    """Name of the integration that found the issue."""

    message: str
    """Human-readable description of the issue."""

    level: str = "warning"
    """Severity: 'warning' or 'error'."""


class Integration(Protocol):
    """Protocol that all integrations implement."""

    name: str
    """Unique name for this integration (e.g., 'npm-workspaces')."""

    default_enabled: bool
    """Whether this integration is enabled by default."""

    def activate(self, ctx: IntegrationContext) -> None:
        """Generate files, run commands, etc. Called by 'reporoot activate'."""
        ...

    def deactivate(self, root: Path) -> None:
        """Clean up generated files. Called by 'reporoot reset'."""
        ...

    def check(self, ctx: IntegrationContext) -> list[Issue]:
        """Inspect workspace state, return issues. Called by 'reporoot check'."""
        ...
