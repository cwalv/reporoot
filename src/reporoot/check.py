"""reporoot check — convention enforcement.

Scans ALL project .repos files (not just the active project) to build the
complete inventory of known repos.  A repo on disk that appears in ANY
project's .repos is not an orphan.

Checks:
1. All git repos under registry dirs are in at least one project's .repos (no orphaned clones)
2. All entries in project .repos files exist on disk (no dangling refs)
3. All entries in project .repos files have a role field
4. Lock file versions match current HEAD hashes (stale lock detection)
5. Integration-specific checks (tool availability, config health)
"""

from pathlib import Path

from reporoot.config import registry_names
from reporoot.git import head_hash
from reporoot.integrations.registry import run_check
from reporoot.workspace import (
    all_known_repos,
    all_project_repos_files,
    find_root,
    project_lock_file,
    read_repos,
    read_repos_full,
    require_active_project,
)


def _find_git_repos(base: Path) -> set[str]:
    """Find all git repos under a directory, returned as relative paths from root."""
    root = base.parent  # base is e.g. root/github, we want paths relative to root
    repos = set()
    for git_dir in sorted(base.rglob(".git")):
        if git_dir.is_dir():
            rel = str(git_dir.parent.relative_to(root))
            repos.add(rel)
    return repos


def _check_missing_roles(repos_file: Path) -> list[str]:
    """Check that each entry in a .repos file has a role field."""
    issues = []
    repos = read_repos(repos_file)
    for repo_path, info in repos.items():
        if "role" not in info:
            issues.append(f"  missing role: {repo_path}")
    return issues


def _check_stale_lock(root: Path, project: str, repos_file: Path) -> list[str]:
    """Compare lock file versions against current HEAD hashes."""
    lock_file = project_lock_file(root, project)
    if not lock_file.exists():
        return []

    lock_repos = read_repos(lock_file)
    if not lock_repos:
        return []

    issues = []
    for repo_path, lock_info in lock_repos.items():
        lock_version = lock_info.get("version", "")
        repo_dir = root / repo_path
        if not repo_dir.is_dir():
            continue
        try:
            current = head_hash(repo_dir)
        except Exception:
            continue
        if lock_version and current and lock_version != current:
            issues.append(
                f"  stale lock: {repo_path} "
                f"(lock={lock_version[:12]}, HEAD={current[:12]})"
            )
    return issues


def run() -> None:
    root = find_root()

    # Build known repos from ALL project .repos files
    known_repos = all_known_repos(root)
    project_files = all_project_repos_files(root)

    issues = 0

    # 1. Orphaned clones: git repos under any registry dir not in any project's .repos
    for reg_name in sorted(registry_names()):
        reg_dir = root / reg_name
        if reg_dir.is_dir():
            on_disk = _find_git_repos(reg_dir)
            orphaned = on_disk - known_repos
            for repo in sorted(orphaned):
                print(f"orphan: {repo} (on disk but not in any project .repos)")
                issues += 1

    # 2. Dangling refs + missing roles + stale locks in each project's .repos
    for project, repos_file in project_files:
        project_repos = read_repos(repos_file)

        # Dangling: listed in project .repos but not on disk
        for repo_path in project_repos:
            repo_dir = root / repo_path
            if not repo_dir.is_dir():
                print(f"dangling: {repos_file.name}: {repo_path} (not on disk)")
                issues += 1

        # Missing role field
        role_issues = _check_missing_roles(repos_file)
        for issue in role_issues:
            print(f"role: {repos_file.name}:{issue}")
            issues += 1

        # Stale lock
        lock_issues = _check_stale_lock(root, project, repos_file)
        for issue in lock_issues:
            print(f"lock: {repos_file.name}:{issue}")
            issues += 1

    # 3. Integration checks (only if there's an active project)
    try:
        active = require_active_project(root)
    except SystemExit:
        active = None

    if active:
        active_repos_file = None
        for proj, rfile in project_files:
            if proj == active:
                active_repos_file = rfile
                break
        if active_repos_file:
            repos = read_repos(active_repos_file)
            full = read_repos_full(active_repos_file)
            integrations_config = full.get("integrations", {})
            integration_issues = run_check(root, active, repos, integrations_config)
            for issue in integration_issues:
                level = issue.level
                print(f"{level}: [{issue.integration}] {issue.message}")
                issues += 1

    if issues == 0:
        print("all checks passed")
    else:
        print(f"\n{issues} issue(s) found")
        raise SystemExit(1)
