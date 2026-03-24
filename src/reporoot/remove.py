"""reporoot remove — remove a repo from a project.

Usage:
  reporoot remove <path>                  Remove from project's reporoot.yaml, re-run integrations
  reporoot remove <path> --project p      Remove from a specific project
  reporoot remove <path> --delete         Also rm -rf the clone from disk
  reporoot remove <path> --delete --force Skip confirmation for disk deletion
"""

from __future__ import annotations

import shutil

from reporoot.git import worktree_remove
from reporoot.integrations.registry import run_activate
from reporoot.workspace import (
    bare_repo_path,
    infer_context,
    project_repos_file,
    read_repos,
    read_repos_full,
    remove_entry,
    workspace_dir,
)


def run(
    path: str,
    project: str | None = None,
    delete: bool = False,
    force: bool = False,
) -> None:
    # Infer context from CWD (root, project, workspace)
    ctx = infer_context()
    root = ctx.root
    in_workspace = ctx.workspace is not None

    target_project = project or ctx.project
    if not target_project:
        raise SystemExit("fatal: cannot determine project (cd into a workspace or use --project)")
    repos_file = project_repos_file(root, target_project)

    # Verify the entry exists before removing
    existing = read_repos(repos_file)
    if path not in existing:
        raise SystemExit(f"fatal: {path} not found in {repos_file.name}")

    print(f"remove: {path}")

    # If in a workspace, remove the worktree first
    if in_workspace and ctx.workspace:
        ws_dir = workspace_dir(root, target_project, ctx.workspace)
        wt_path = ws_dir / path
        if wt_path.exists():
            bare = bare_repo_path(root, path)
            worktree_remove(bare, wt_path, force=True)
            print(f"  removed worktree: {path}")
        else:
            print(f"  worktree not found in workspace: {path}")
        # Bare repo stays — it's a shared resource that may be used by other workspaces

    remove_entry(repos_file, path)

    # Optionally delete the clone from disk (only for non-workspace / legacy clones)
    if delete:
        clone_path = root / path
        if clone_path.exists():
            if not force:
                answer = input(f"  delete {clone_path}? [y/N] ")
                if answer.lower() not in ("y", "yes"):
                    print("  skipped disk deletion")
                    return
            shutil.rmtree(clone_path)
            print(f"  deleted {path} from disk")
        else:
            print(f"  {path} not on disk, nothing to delete")

    # Regenerate integration files
    repos = read_repos(repos_file)
    full = read_repos_full(repos_file)
    integrations_config = full.get("integrations", {})
    # If in a workspace, target integration activation at the workspace dir
    if in_workspace and ctx.workspace:
        activate_root = workspace_dir(root, target_project, ctx.workspace)
    else:
        activate_root = root
    run_activate(activate_root, target_project, repos, integrations_config)
