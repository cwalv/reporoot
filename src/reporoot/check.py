"""reporoot check — convention enforcement.

Scans ALL project reporoot.yaml files (not just the active project) to build
the complete inventory of known repos.  A repo on disk that appears in ANY
project's reporoot.yaml is not an orphan.

Checks:
1. All git repos under registry dirs are in at least one project (no orphaned clones)
2. All bare repos under registry dirs are in at least one project (no orphaned bare repos)
3. All entries in project reporoot.yaml files exist on disk (no dangling refs — clone or bare)
4. All entries have a role field
5. Lock file versions match current HEAD hashes (stale lock detection)
6. Integration-specific checks (tool availability, config health)
"""

from pathlib import Path

from reporoot.config import registry_names
from reporoot.git import head_hash
from reporoot.integrations.registry import run_check
from reporoot.workspace import (
    all_known_repos,
    all_project_repos_files,
    bare_repo_path,
    find_git_repos,
    find_root,
    project_lock_file,
    read_repos,
    read_repos_full,
    require_active_project,
)


def find_bare_repos(base: Path) -> set[str]:
    """Find all bare repos (*.git dirs) under a directory, returned as logical repo paths.

    ``base`` is a registry directory (e.g., root/github).  Returns logical
    paths relative to ``base.parent`` (the reporoot), with the .git suffix
    stripped.  e.g., github/owner/repo.git -> github/owner/repo.

    Excludes ``.git`` directories inside regular clones (hidden dirs whose
    name is exactly ``.git``).
    """
    root = base.parent
    repos: set[str] = set()
    for path in sorted(base.rglob("*.git")):
        if path.is_dir() and path.name != ".git":
            # Convert bare repo dir to logical repo path
            rel = str(path.relative_to(root))
            logical = rel.removesuffix(".git")
            repos.add(logical)
    return repos


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
        # Try bare repo first, then regular clone
        bare = bare_repo_path(root, repo_path)
        repo_dir = bare if bare.is_dir() else root / repo_path
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
    orphan_bare: list[str] = []
    dangling: list[tuple[str, str]] = []  # (project, repo_path)
    dangling_bare: list[tuple[str, str]] = []  # (project, repo_path)
    missing_roles: list[tuple[str, str]] = []  # (project, repo_path)
    stale_locks: list[tuple[str, str]] = []  # (project, detail)
    integration_issues_list: list[str] = []

    # 1. Orphaned clones and bare repos
    for reg_name in sorted(registry_names()):
        reg_dir = root / reg_name
        if reg_dir.is_dir():
            on_disk = find_git_repos(reg_dir)
            orphans.extend(sorted(on_disk - known_repos))

            bare_on_disk = find_bare_repos(reg_dir)
            orphan_bare.extend(sorted(bare_on_disk - known_repos))

    # 2. Per-project checks
    for project, repos_file in project_files:
        project_repos = read_repos(repos_file)

        for repo_path in project_repos:
            clone_exists = (root / repo_path).is_dir()
            bare_exists = bare_repo_path(root, repo_path).is_dir()
            if not clone_exists and not bare_exists:
                dangling.append((project, repo_path))
            elif not bare_exists:
                dangling_bare.append((project, repo_path))

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

    if orphan_bare:
        total += len(orphan_bare)
        if verbose:
            for repo in orphan_bare:
                print(f"orphan-bare: {repo}")
        else:
            print(f"orphan-bare: {len(orphan_bare)} bare repo(s) on disk but not in any project")

    if dangling:
        total += len(dangling)
        if verbose:
            for project, repo_path in dangling:
                print(f"dangling: {project}: {repo_path} (not on disk)")
        else:
            print(f"dangling: {len(dangling)} repo(s) listed but not on disk")

    if dangling_bare:
        total += len(dangling_bare)
        if verbose:
            for project, repo_path in dangling_bare:
                print(f"dangling-bare: {project}: {repo_path} (no bare repo)")
        else:
            print(f"dangling-bare: {len(dangling_bare)} repo(s) missing bare repo")

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
