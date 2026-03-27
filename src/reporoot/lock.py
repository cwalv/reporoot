"""reporoot lock — regenerate lock file with exact commit hashes.

reporoot lock      → lock the active project from the current workspace
reporoot lock-all  → lock all projects on disk (reads bare repos)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from reporoot.git import GitError, export_repo
from reporoot.workspace import (
    all_project_repos_files,
    bare_repo_path,
    default_workspace_name,
    find_root,
    project_lock_file,
    project_repos_file,
    read_repos,
    require_context,
    workspace_dir,
)


def _export_one(
    root: Path,
    local_path: str,
    ws_dir: Path | None = None,
) -> tuple[str, dict[str, str] | str]:
    """Export one repo. Returns (local_path, export_data_or_error_string).

    Resolution order:
    1. Workspace worktree (if ws_dir provided)
    2. Bare repo (github/owner/repo.git)
    3. Legacy clone (github/owner/repo)
    """
    # 1. Workspace worktree
    if ws_dir is not None:
        wt = ws_dir / local_path
        if wt.is_dir():
            try:
                data = export_repo(wt)
                return local_path, data
            except GitError as e:
                return local_path, str(e)

    # 2. Bare repo
    bare = bare_repo_path(root, local_path)
    if bare.is_dir():
        try:
            data = export_repo(bare)
            return local_path, data
        except GitError as e:
            return local_path, str(e)

    # 3. Legacy clone
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


def _lock_project(
    root: Path,
    project: str,
    repos_file: Path,
    ws_dir: Path | None = None,
) -> int:
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
        futures = {
            pool.submit(_export_one, root, path, ws_dir): path
            for path in repos
        }
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


def run(
    project: str | None = None,
    workspace: str | None = None,
) -> None:
    """Lock the active project from the current workspace."""
    ctx = require_context(project=project, workspace=workspace)
    repos_file = project_repos_file(ctx.root, ctx.project)
    if not repos_file.exists():
        raise SystemExit(f"fatal: no reporoot.yaml found for project '{ctx.project}'")
    ws = workspace_dir(ctx.root, ctx.project, ctx.workspace)
    print(f"lock: {ctx.project}")
    errors = _lock_project(ctx.root, ctx.project, repos_file, ws_dir=ws)
    if errors:
        raise SystemExit(f"fatal: {errors} repo(s) could not be exported")


def run_all() -> None:
    """Lock all projects on disk, using each project's default workspace."""
    root = find_root()
    projects = all_project_repos_files(root)
    if not projects:
        print("lock-all: no projects found")
        return

    print(f"lock-all: {len(projects)} project(s)")
    total_errors = 0
    for project, repos_file in projects:
        ws_name = default_workspace_name(root, project)
        ws = workspace_dir(root, project, ws_name)
        ws_dir_opt = ws if ws.is_dir() else None
        total_errors += _lock_project(root, project, repos_file, ws_dir=ws_dir_opt)
    if total_errors:
        raise SystemExit(f"fatal: {total_errors} repo(s) could not be exported")
