"""reporoot activate — set the active project and run integration hooks.

Usage:
  reporoot activate web-app     Set active project, run integrations (npm, go, gita, etc.)
  reporoot activate none        Deactivate, remove generated files
"""

from __future__ import annotations

from pathlib import Path

import shutil
import sys

from reporoot.config import registry_names
from reporoot.integrations.registry import run_activate, run_deactivate
from reporoot.workspace import (
    active_project,
    find_root,
    project_repos_file,
    read_repos,
    read_repos_full,
)

# Dirs at root that are never removed by --hard
_ALWAYS_KEEP = {"projects"}


def reset(hard: bool = False, force: bool = False) -> None:
    """Deactivate: remove derived files, clear .rr-active pointer.

    With hard=True, also removes everything at root that isn't a known
    registry directory or projects/ — tool state like node_modules,
    .venv, lock files, etc.  Each item is confirmed interactively
    unless force=True.
    """
    root = find_root()
    print("reset: deactivating")
    active_file = root / ".rr-active"
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


def run(project: str) -> None:
    root = find_root()

    if project == "none":
        reset()
        return

    # Validate project exists
    repos_file = project_repos_file(root, project)
    if not repos_file.exists():
        raise SystemExit(f"fatal: no {repos_file.name} found in projects/{project}/")

    # Check if already active
    current = active_project(root)
    if current == project:
        print(f"activate: {project} (already active, regenerating)")
    else:
        print(f"activate: {project}")

    # Write .rr-active
    (root / ".rr-active").write_text(project + "\n")

    # Read repos and integration config
    repos = read_repos(repos_file)
    repos_full = read_repos_full(repos_file)
    integrations_config = repos_full.get("integrations", {})

    # Run integration activation hooks
    ran = run_activate(root, project, repos, integrations_config)
    if not ran:
        print("  no integrations ran")
