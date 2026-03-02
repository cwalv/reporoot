"""reporoot add — add a repo to the active project.

Usage:
  reporoot add <url>                              Clone from URL to {registry}/{owner}/{repo}/
  reporoot add <local-path>                       Move local repo (reads its remote)
  reporoot add <source> --role r                  Set role
  reporoot add <source> --project p               Add to a specific project (override active)
  reporoot add <source> --as-project name         Add as a project repo to projects/{name}/
"""

from __future__ import annotations

from pathlib import Path

from reporoot.config import normalize_repo_url, parse_repo_url
from reporoot.git import GitError, clone, clone_local, default_branch, remote_url
from reporoot.integrations.registry import run_activate
from reporoot.workspace import (
    append_entry,
    find_root,
    project_repos_file,
    read_repos,
    read_repos_full,
    require_active_project,
)


def _is_url(source: str) -> bool:
    return source.startswith(("https://", "http://", "git@"))


def _is_local_repo(source: str) -> bool:
    p = Path(source).expanduser().resolve()
    return p.is_dir() and (p / ".git").exists()


def run(
    source: str,
    project: str | None = None,
    role: str | None = None,
    note: str | None = None,
    as_project: str | None = None,
) -> None:
    root = find_root()

    # Resolve source to a URL + registry/owner/repo
    if _is_url(source):
        url = source
        registry, owner, repo = parse_repo_url(url)
        source_path = None
    elif _is_local_repo(source):
        source_path = Path(source).expanduser().resolve()
        url = remote_url(source_path)
        registry, owner, repo = parse_repo_url(url)
    else:
        raise SystemExit(f"fatal: {source} is not a URL or a local git repo")

    canonical_url = normalize_repo_url(registry, owner, repo)

    # Determine target path
    if as_project:
        local_path = f"projects/{as_project}"
        target = root / local_path
    else:
        local_path = f"{registry}/{owner}/{repo}"
        target = root / local_path

    if target.exists():
        raise SystemExit(f"fatal: target already exists: {target}")

    # Clone or move
    print(f"add: {local_path}")
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        if source_path:
            print(f"  git clone --local {source_path} -> {target}")
            clone_local(source_path, target, canonical_url)
        else:
            print(f"  git clone {url} -> {target}")
            clone(url, target)
    except GitError as e:
        raise SystemExit(f"fatal: {e}")

    version = default_branch(target)

    # Add to project .repos file
    if not as_project:
        # Determine which project to add to
        target_project = project or require_active_project(root)
        repos_file = project_repos_file(root, target_project)
        if not repos_file.parent.exists():
            print(f"  warning: project dir projects/{target_project}/ does not exist, skipping .repos update")
        else:
            append_entry(repos_file, local_path, canonical_url, version, role=role, note=note)
            # Regenerate integration files
            repos = read_repos(repos_file)
            full = read_repos_full(repos_file)
            integrations_config = full.get("integrations", {})
            run_activate(root, target_project, repos, integrations_config)
