"""reporoot remove — remove a repo from a project.

Usage:
  reporoot remove <path>                  Remove from active project's .repos, re-run activate
  reporoot remove <path> --project p      Remove from a specific project
  reporoot remove <path> --delete         Also rm -rf the clone from disk
  reporoot remove <path> --delete --force Skip confirmation for disk deletion
"""

from __future__ import annotations

import shutil

from reporoot.integrations.registry import run_activate
from reporoot.workspace import (
    find_root,
    project_repos_file,
    read_repos,
    read_repos_full,
    remove_entry,
    require_active_project,
)


def run(
    path: str,
    project: str | None = None,
    delete: bool = False,
    force: bool = False,
) -> None:
    root = find_root()
    target_project = project or require_active_project(root)
    repos_file = project_repos_file(root, target_project)

    # Verify the entry exists before removing
    existing = read_repos(repos_file)
    if path not in existing:
        raise SystemExit(f"fatal: {path} not found in {repos_file.name}")

    print(f"remove: {path}")
    remove_entry(repos_file, path)

    # Optionally delete the clone from disk
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
    run_activate(root, target_project, repos, integrations_config)
