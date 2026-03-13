"""Integration registry — discovers and dispatches to integrations."""

from __future__ import annotations

from pathlib import Path

from reporoot.integrations.base import Integration, IntegrationContext, Issue


def _all_integrations() -> list[Integration]:
    """Return instances of all built-in integrations."""
    from reporoot.integrations.claude_md import ClaudeMd
    from reporoot.integrations.gita import Gita
    from reporoot.integrations.go_work import GoWork
    from reporoot.integrations.npm_workspaces import NpmWorkspaces
    from reporoot.integrations.uv_workspace import UvWorkspace
    from reporoot.integrations.vscode_workspace import VscodeWorkspace

    return [
        NpmWorkspaces(),
        GoWork(),
        UvWorkspace(),
        Gita(),
        VscodeWorkspace(),
        ClaudeMd(),
    ]


def resolve_enabled(integrations_config: dict) -> list[Integration]:
    """Return the list of integrations that should be active.

    Uses each integration's default_enabled, overridden by the
    per-project 'integrations' config from reporoot.yaml.
    """
    result = []
    for integration in _all_integrations():
        cfg = integrations_config.get(integration.name, {})
        enabled = cfg.get("enabled", integration.default_enabled)
        if enabled:
            result.append(integration)
    return result


def _build_shared_context(root: Path) -> tuple[set[str], list[str]]:
    """Compute shared data for IntegrationContext (cached per invocation)."""
    from reporoot.config import registry_names
    from reporoot.workspace import all_project_repos_files, find_git_repos

    all_on_disk: set[str] = set()
    for reg_name in registry_names():
        reg_dir = root / reg_name
        if reg_dir.is_dir():
            all_on_disk |= find_git_repos(reg_dir)

    all_projects = [name for name, _path in all_project_repos_files(root)]

    return all_on_disk, all_projects


def run_activate(
    root: Path,
    project: str,
    repos: dict[str, dict],
    integrations_config: dict,
) -> list[str]:
    """Run activation hooks for all enabled integrations.

    Returns list of names of integrations that ran.
    """
    enabled = resolve_enabled(integrations_config)
    all_on_disk, all_projects = _build_shared_context(root)
    ran = []
    for integration in enabled:
        print(f"  [{integration.name}]")
        ctx = IntegrationContext(
            root=root,
            project=project,
            repos=repos,
            config=integrations_config.get(integration.name, {}),
            all_repos_on_disk=all_on_disk,
            all_project_paths=all_projects,
        )
        integration.activate(ctx)
        ran.append(integration.name)
    return ran


def run_deactivate(root: Path) -> None:
    """Run deactivation hooks for ALL integrations (regardless of config)."""
    for integration in _all_integrations():
        integration.deactivate(root)


def run_check(
    root: Path,
    project: str,
    repos: dict[str, dict],
    integrations_config: dict,
) -> list[Issue]:
    """Run check hooks for all enabled integrations.

    Returns collected issues from all integrations.
    """
    enabled = resolve_enabled(integrations_config)
    all_on_disk, all_projects = _build_shared_context(root)
    issues: list[Issue] = []
    for integration in enabled:
        ctx = IntegrationContext(
            root=root,
            project=project,
            repos=repos,
            config=integrations_config.get(integration.name, {}),
            all_repos_on_disk=all_on_disk,
            all_project_paths=all_projects,
        )
        issues.extend(integration.check(ctx))
    return issues
