"""reporoot lock — regenerate lock file with exact commit hashes.

reporoot lock      → lock the active project
reporoot lock-all  → lock all projects on disk
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from reporoot.git import GitError, export_repo
from reporoot.workspace import (
    active_repos_file,
    all_project_repos_files,
    find_root,
    project_lock_file,
    read_repos,
)


def _export_one(root: Path, local_path: str) -> tuple[str, dict[str, str] | str]:
    """Export one repo. Returns (local_path, export_data_or_error_string)."""
    repo_dir = root / local_path
    if not repo_dir.is_dir():
        return local_path, f"missing: {local_path} (not cloned)"
    if not (repo_dir / ".git").exists():
        return local_path, f"not a git repo: {local_path}"
    try:
        data = export_repo(repo_dir)
        return local_path, data
    except GitError as e:
        return local_path, str(e)


def _lock_project(root: Path, project: str, repos_file: Path) -> int:
    """Generate the lock file for a single project. Returns number of errors."""
    lock_file = project_lock_file(root, project)
    repos = read_repos(repos_file)
    if not repos:
        print(f"  skip {project}: {repos_file.name} is empty")
        return 0

    print(f"  {project}: exporting {len(repos)} repos")

    results: dict[str, dict[str, str]] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_export_one, root, path): path for path in repos}
        for future in as_completed(futures):
            path, data = future.result()
            if isinstance(data, str):
                errors.append(data)
                print(f"    error: {data}")
            else:
                results[path] = data

    if errors:
        print(f"    {len(errors)} repo(s) failed")
        return len(errors)

    # Emit YAML in sorted order
    lines = ["repositories:"]
    for path in sorted(results):
        data = results[path]
        lines.append(f"  {path}:")
        lines.append("    type: git")
        lines.append(f"    url: {data['url']}")
        lines.append(f"    version: {data['version']}")
    output = "\n".join(lines) + "\n"

    lock_file.write_text(output)
    print(f"    wrote {lock_file.name} ({len(results)} repos)")
    return 0


def run() -> None:
    """Lock the active project."""
    root = find_root()
    repos_file = active_repos_file(root)
    project = repos_file.parent.name
    print(f"lock: {project}")
    errors = _lock_project(root, project, repos_file)
    if errors:
        raise SystemExit(f"fatal: {errors} repo(s) could not be exported")


def run_all() -> None:
    """Lock all projects on disk."""
    root = find_root()
    projects = all_project_repos_files(root)
    if not projects:
        print("lock-all: no projects found")
        return

    print(f"lock-all: {len(projects)} project(s)")
    total_errors = 0
    for project, repos_file in projects:
        total_errors += _lock_project(root, project, repos_file)
    if total_errors:
        raise SystemExit(f"fatal: {total_errors} repo(s) could not be exported")
