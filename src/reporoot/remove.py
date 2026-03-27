"""reporoot remove — remove a repo from a project.

Usage:
  reporoot remove <path>                  Remove from project's reporoot.yaml, re-run integrations
  reporoot remove <path> --project p      Remove from a specific project
  reporoot remove <path> --workspace w    Target a specific workspace
  reporoot remove <path> --delete         Also rm -rf the bare repo from disk
  reporoot remove <path> --delete --force Skip confirmation for disk deletion
"""

from __future__ import annotations

import shutil

from reporoot.git import worktree_remove
from reporoot.integrations.registry import run_activate
from reporoot.workspace import (
    bare_repo_path,
    project_repos_file,
    read_repos,
    read_repos_full,
    remove_entry,
    require_context,
    workspace_dir,
)


def run(
    path: str,
    project: str | None = None,
    workspace: str | None = None,
    delete: bool = False,
    force: bool = False,
) -> None:
    ctx = require_context(project=project, workspace=workspace)
    root = ctx.root
    repos_file = project_repos_file(root, ctx.project)

    # Verify the entry exists before removing
    existing = read_repos(repos_file)
    if path not in existing:
        raise SystemExit(f"fatal: {path} not found in {repos_file.name}")

    print(f"remove: {path}")

    # Remove the worktree from the workspace
    ws_dir = workspace_dir(root, ctx.project, ctx.workspace)
    wt_path = ws_dir / path
    if wt_path.exists():
        bare = bare_repo_path(root, path)
        worktree_remove(bare, wt_path, force=True)
        print(f"  removed worktree: {path}")
    else:
        print(f"  worktree not found in workspace: {path}")

    remove_entry(repos_file, path)

    # Optionally delete the bare repo from disk
    if delete:
        bare = bare_repo_path(root, path)
        if bare.exists():
            if not force:
                answer = input(f"  delete {bare}? [y/N] ")
                if answer.lower() not in ("y", "yes"):
                    print("  skipped disk deletion")
                    return
            shutil.rmtree(bare)
            print(f"  deleted {bare.name} from disk")
        else:
            print(f"  {path} not on disk, nothing to delete")

    # Regenerate integration files
    repos = read_repos(repos_file)
    full = read_repos_full(repos_file)
    integrations_config = full.get("integrations", {})
    activate_root = workspace_dir(root, ctx.project, ctx.workspace)
    run_activate(activate_root, ctx.project, repos, integrations_config)
