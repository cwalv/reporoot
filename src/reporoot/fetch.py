"""reporoot fetch — clone a project repo and import its repos.

Usage:
  reporoot fetch cwalv/agent-relay                   owner/project (default registry)
  reporoot fetch github/cwalv/agent-relay             registry/owner/project
  reporoot fetch https://github.com/cwalv/agent-relay full URL

Clones the project repo to projects/{project}/, reads reporoot.yaml,
bare-clones all listed repos, and creates a default workspace.  If run
outside an existing reporoot, bootstraps cwd as a new root.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from reporoot.config import normalize_repo_url, parse_repo_url, resolve_shorthand
from reporoot.git import GitError, clone, clone_or_update
from reporoot.workspace import (
    REPOS_FILE,
    bare_repo_path,
    create_workspace,
    find_root,
    read_repos,
)


def _is_url(source: str) -> bool:
    return source.startswith(("https://", "http://", "git@", "file://"))


def _import_one(
    root: Path,
    local_path: str,
    info: dict,
) -> tuple[str, str]:
    """Import one repo as a bare clone. Returns (local_path, status_message).

    If a regular (non-bare) clone already exists at the canonical path,
    it is left as-is for backward compatibility.
    """
    url = info.get("url", "")
    version = info.get("version")
    regular_target = root / local_path

    # Backward compat: if a regular clone exists, leave it alone
    if regular_target.exists():
        try:
            status = clone_or_update(url, regular_target, version, skip_existing=True)
            return local_path, status
        except GitError as e:
            return local_path, f"error: {e}"

    # Create bare clone
    bare_target = bare_repo_path(root, local_path)
    try:
        status = clone_or_update(url, bare_target, skip_existing=True, bare=True)
        return local_path, status
    except GitError as e:
        return local_path, f"error: {e}"


def run(source: str) -> None:
    # Detect argument form:
    # 1. Full URL: starts with https://, http://, git@
    # 2. registry/owner/project: 3 segments
    # 3. owner/project: 2 segments (default registry)
    owner: str | None = None
    if _is_url(source):
        registry, owner, project = parse_repo_url(source)
        url = source
    else:
        parts = source.split("/")
        if len(parts) == 3:
            registry, owner, project = parts
            url = normalize_repo_url(registry, owner, project)
        elif len(parts) == 2:
            owner, project = parts
            url, _ = resolve_shorthand(source)
        else:
            raise SystemExit(f"fatal: expected URL, registry/owner/project, or owner/project, got: {source}")

    try:
        root = find_root()
    except SystemExit:
        # Bootstrap: on a fresh machine, use cwd as root
        root = Path.cwd().resolve()
        (root / "projects").mkdir(exist_ok=True)

    target = root / "projects" / project

    # Handle existing project dir gracefully: if the project dir exists
    # but repos may be missing, skip the project clone and process repos.
    project_already_exists = target.exists()

    if not project_already_exists:
        # Clone the project repo
        print(f"fetch: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        print(f"  git clone {url} -> projects/{project}/")
        try:
            clone(url, target)
        except GitError as e:
            raise SystemExit(f"fatal: {e}")
    else:
        print(f"fetch: {source} (project dir exists, processing repos)")

    # Read the project's reporoot.yaml and import
    repos_file = target / REPOS_FILE
    if not repos_file.exists():
        print(f"  warning: no {REPOS_FILE} found in project repo")
        return

    repos = read_repos(repos_file)
    if not repos:
        print(f"  warning: {REPOS_FILE} is empty")
        return

    print(f"  importing {len(repos)} repos from {REPOS_FILE}")

    # Import repos as bare clones in parallel
    errors = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_import_one, root, path, info): path for path, info in repos.items()}
        for future in as_completed(futures):
            path, status = future.result()
            print(f"    {path}: {status}")
            if status.startswith("error:"):
                errors += 1

    if errors:
        print(f"  warning: {errors} repo(s) had errors")

    # Create default workspace (worktrees from bare repos)
    print()
    print(f"  creating default workspace for {project}")
    try:
        ws = create_workspace(root, project, "default")
        print(f"  workspace ready: {ws}")
    except SystemExit:
        # Workspace may already exist (e.g., re-fetching an existing project)
        print("  default workspace already exists, skipping")
