"""reporoot integrations — pluggable activation and check hooks."""

from reporoot.integrations.base import Integration, IntegrationContext, Issue
from reporoot.integrations.registry import resolve_enabled, run_activate, run_check

__all__ = [
    "Integration",
    "IntegrationContext",
    "Issue",
    "resolve_enabled",
    "run_activate",
    "run_check",
]
