"""reporoot fetch — clone a project repo and import its repos.

Usage:
  reporoot fetch cwalv/agent-relay                   owner/project (default registry)
  reporoot fetch github/cwalv/agent-relay             registry/owner/project
  reporoot fetch https://github.com/cwalv/agent-relay full URL

Clones the project repo to projects/{project}/, reads reporoot.yaml,
imports all listed repos, and activates the project.  If run outside an
existing reporoot, bootstraps cwd as a new root.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from reporoot.activate import run as activate
from reporoot.config import normalize_repo_url, parse_repo_url, resolve_shorthand
from reporoot.git import GitError, clone, clone_or_update
from reporoot.workspace import REPOS_FILE, find_root, read_repos


def _is_url(source: str) -> bool:
    return source.startswith(("https://", "http://", "git@", "file://"))


def _import_one(
    root: Path,
    local_path: str,
    info: dict,
) -> tuple[str, str]:
    """Import one repo. Returns (local_path, status_message)."""
    url = info.get("url", "")
    version = info.get("version")
    target = root / local_path
    try:
        status = clone_or_update(url, target, version, skip_existing=True)
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

    if target.exists():
        msg = f"fatal: project already exists: projects/{project}/"
        if owner:
            msg += f"\nhint: to scope under owner, clone manually to projects/{owner}/{project}/"
        raise SystemExit(msg)

    # Clone the project repo
    print(f"fetch: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"  git clone {url} -> projects/{project}/")
    try:
        clone(url, target)
    except GitError as e:
        raise SystemExit(f"fatal: {e}")

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

    # Import repos in parallel
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

    # Activate the fetched project
    print()
    activate(project=project)
