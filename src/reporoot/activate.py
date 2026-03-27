"""reporoot workspace — create, delete, sync, and list workspaces.

Usage:
  reporoot workspace myproject             Create default workspace, run integrations
  reporoot workspace myproject dev         Create named workspace
  reporoot workspace myproject --delete    Delete default workspace
  reporoot workspace myproject --sync      Sync default workspace with manifest
  reporoot workspace myproject --list      List workspaces for project
"""

from __future__ import annotations

from reporoot.integrations.registry import run_activate, run_deactivate
from reporoot.workspace import (
    create_workspace,
    delete_workspace,
    find_root,
    list_workspaces,
    project_repos_file,
    read_repos,
    read_repos_full,
    sync_workspace,
    workspace_dir,
)


def workspace_run(
    project: str,
    name: str | None = None,
    *,
    delete: bool = False,
    sync: bool = False,
) -> None:
    """Create, delete, or sync a workspace for a project.

    Default (no flags): create workspace and run integration activation.
    --delete: delete workspace and run integration deactivation.
    --sync: sync workspace worktrees with the project manifest.
    """
    from reporoot.workspace import default_workspace_name

    root = find_root()
    if name is None:
        name = default_workspace_name(root, project)

    if delete:
        ws = workspace_dir(root, project, name)
        run_deactivate(ws)
        delete_workspace(root, project, name)
        return

    if sync:
        sync_workspace(root, project, name)
        return

    # Create workspace
    ws = create_workspace(root, project, name)

    # Read repos and integration config, then run activation
    repos_file = project_repos_file(root, project)
    repos = read_repos(repos_file)
    repos_full = read_repos_full(repos_file)
    integrations_config = repos_full.get("integrations", {})

    ran = run_activate(ws, project, repos, integrations_config)
    if not ran:
        print("  no integrations ran")


def workspace_list(project: str) -> list[str]:
    """List workspaces for a project and print them."""
    root = find_root()
    names = list_workspaces(root, project)
    if not names:
        print(f"no workspaces for project '{project}'")
    else:
        for name in names:
            print(f"  {name}")
    return names


