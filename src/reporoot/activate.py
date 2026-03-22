"""reporoot workspace — create, delete, sync, and list workspaces.

Usage:
  reporoot workspace myproject             Create default workspace, run integrations
  reporoot workspace myproject dev         Create named workspace
  reporoot workspace myproject --delete    Delete default workspace
  reporoot workspace myproject --sync      Sync default workspace with manifest
  reporoot workspace myproject --list      List workspaces for project

Backward-compat (migration period):
  reporoot activate <project>              Old single-project activation
  reporoot deactivate [--hard] [--force]   Old deactivation
"""

from __future__ import annotations

import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from reporoot.config import registry_names
from reporoot.git import GitError, clone_or_update
from reporoot.integrations.registry import run_activate, run_deactivate
from reporoot.workspace import (
    REPOS_FILE,
    active_project,
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

# Dirs at root that are never removed by --hard
_ALWAYS_KEEP = {"projects"}


# --- Workspace commands ---


def workspace_run(
    project: str,
    name: str = "default",
    *,
    delete: bool = False,
    sync: bool = False,
) -> None:
    """Create, delete, or sync a workspace for a project.

    Default (no flags): create workspace and run integration activation.
    --delete: delete workspace and run integration deactivation.
    --sync: sync workspace worktrees with the project manifest.
    """
    root = find_root()

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


# --- Backward-compat (migration period) ---


def deactivate(hard: bool = False, force: bool = False) -> None:
    """Deactivate: remove derived files, clear .reporoot-active pointer.

    With hard=True, also removes everything at root that isn't a known
    registry directory or projects/ — tool state like node_modules,
    .venv, lock files, etc.  Each item is confirmed interactively
    unless force=True.
    """
    root = find_root()
    print("deactivate: removing derived files")
    active_file = root / ".reporoot-active"
    if active_file.exists():
        active_file.unlink()
    run_deactivate(root)

    if hard:
        _hard_clean(root, force=force)


def _confirm(prompt: str) -> bool:
    """Prompt user for y/n confirmation. Returns True if yes."""
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def _hard_clean(root: Path, *, force: bool) -> None:
    """Remove everything at root that isn't a known registry dir or projects/."""
    keep = _ALWAYS_KEEP | registry_names()
    candidates: list[Path] = []
    for entry in sorted(root.iterdir()):
        if entry.name in keep:
            continue
        if entry.name.startswith("."):
            continue
        candidates.append(entry)

    if not candidates:
        print("  hard reset: nothing extra to remove")
        return

    if not force and not sys.stdin.isatty():
        print("  hard reset: skipped (not a terminal, use --force)")
        return

    removed: list[str] = []
    for entry in candidates:
        kind = "directory" if entry.is_dir() else "file"
        if not force and not _confirm(f"  remove {kind} {entry.name}?"):
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed.append(entry.name)

    if removed:
        print(f"  hard reset: removed {', '.join(removed)}")
    else:
        print("  hard reset: nothing removed")


def _clone_missing(root: Path, repos: dict[str, dict]) -> None:
    """Clone any repos that are declared but not present on disk."""
    missing = {path: info for path, info in repos.items() if not (root / path).exists() and info.get("url")}
    if not missing:
        return

    print(f"  cloning {len(missing)} missing repo(s)")
    errors = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(
                clone_or_update,
                info["url"],
                root / path,
                info.get("version"),
                skip_existing=True,
            ): path
            for path, info in missing.items()
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                status = future.result()
                print(f"    {path}: {status}")
            except GitError as e:
                errors += 1
                print(f"    {path}: error: {e}")
    if errors:
        raise SystemExit(f"fatal: {errors} repo(s) failed to clone")


def run(project: str, *, fetch: bool = True) -> None:
    root = find_root()

    # Validate project exists
    repos_file = project_repos_file(root, project)
    if not repos_file.exists():
        raise SystemExit(f"fatal: no {REPOS_FILE} found in projects/{project}/")

    # Check if already active
    current = active_project(root)
    if current == project:
        print(f"activate: {project} (already active, regenerating)")
    else:
        print(f"activate: {project}")

    # Write .reporoot-active
    (root / ".reporoot-active").write_text(project + "\n")

    # Read repos and integration config
    repos = read_repos(repos_file)
    repos_full = read_repos_full(repos_file)
    integrations_config = repos_full.get("integrations", {})

    # Clone missing repos
    if fetch:
        _clone_missing(root, repos)

    # Run integration activation hooks
    ran = run_activate(root, project, repos, integrations_config)
    if not ran:
        print("  no integrations ran")
