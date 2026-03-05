"""reporoot check — convention enforcement.

Scans ALL project reporoot.yaml files (not just the active project) to build
the complete inventory of known repos.  A repo on disk that appears in ANY
project's reporoot.yaml is not an orphan.

Checks:
1. All git repos under registry dirs are in at least one project (no orphaned clones)
2. All entries in project reporoot.yaml files exist on disk (no dangling refs)
3. All entries have a role field
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
    find_git_repos,
    find_root,
    project_lock_file,
    read_repos,
    read_repos_full,
    require_active_project,
)


def _check_missing_roles(repos_file: Path) -> list[str]:
    """Check that each entry has a role field."""
    issues = []
    repos = read_repos(repos_file)
    for repo_path, info in repos.items():
        if "role" not in info:
            issues.append(repo_path)
    return issues


def _check_stale_lock(root: Path, project: str) -> list[str]:
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
            issues.append(f"{repo_path} (lock={lock_version[:12]}, HEAD={current[:12]})")
    return issues


def run(verbose: bool = False) -> None:
    root = find_root()

    # Build known repos from ALL project reporoot.yaml files
    known_repos = all_known_repos(root)
    project_files = all_project_repos_files(root)

    # Collect all issues by category
    orphans: list[str] = []
    dangling: list[tuple[str, str]] = []  # (project, repo_path)
    missing_roles: list[tuple[str, str]] = []  # (project, repo_path)
    stale_locks: list[tuple[str, str]] = []  # (project, detail)
    integration_issues_list: list[str] = []

    # 1. Orphaned clones
    for reg_name in sorted(registry_names()):
        reg_dir = root / reg_name
        if reg_dir.is_dir():
            on_disk = find_git_repos(reg_dir)
            orphans.extend(sorted(on_disk - known_repos))

    # 2. Per-project checks
    for project, repos_file in project_files:
        project_repos = read_repos(repos_file)

        for repo_path in project_repos:
            if not (root / repo_path).is_dir():
                dangling.append((project, repo_path))

        for repo_path in _check_missing_roles(repos_file):
            missing_roles.append((project, repo_path))

        for detail in _check_stale_lock(root, project):
            stale_locks.append((project, detail))

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
            for issue in run_check(root, active, repos, integrations_config):
                integration_issues_list.append(f"{issue.level}: [{issue.integration}] {issue.message}")

    # Print results
    total = 0

    if orphans:
        total += len(orphans)
        if verbose:
            for repo in orphans:
                print(f"orphan: {repo}")
        else:
            print(f"orphan: {len(orphans)} repo(s) on disk but not in any project")

    if dangling:
        total += len(dangling)
        if verbose:
            for project, repo_path in dangling:
                print(f"dangling: {project}: {repo_path} (not on disk)")
        else:
            print(f"dangling: {len(dangling)} repo(s) listed but not on disk")

    if missing_roles:
        total += len(missing_roles)
        if verbose:
            for project, repo_path in missing_roles:
                print(f"role: {project}: {repo_path} missing role")
        else:
            print(f"role: {len(missing_roles)} repo(s) missing role field")

    if stale_locks:
        total += len(stale_locks)
        if verbose:
            for project, detail in stale_locks:
                print(f"lock: {project}: {detail}")
        else:
            print(f"lock: {len(stale_locks)} repo(s) with stale lock")

    if integration_issues_list:
        total += len(integration_issues_list)
        for msg in integration_issues_list:
            print(msg)

    if total == 0:
        print("all checks passed")
    else:
        hint = "" if verbose else " (use -v for details)"
        print(f"\n{total} issue(s) found{hint}")
        raise SystemExit(1)
