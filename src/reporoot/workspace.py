"""reporoot utilities: finding the root, reading/writing .repos files, active project."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse


def find_root(start: Path | None = None) -> Path:
    """Walk up from start (default: cwd) looking for a reporoot.

    A reporoot is identified by having a projects/ directory, an .reporoot-active
    file, or any known registry directory (github/, gitlab/, etc.).
    """
    from reporoot.config import registry_names

    p = (start or Path.cwd()).resolve()
    names = registry_names()
    while True:
        if (p / "projects").is_dir() or (p / ".reporoot-active").exists():
            return p
        for name in names:
            if (p / name).is_dir():
                return p
        if p.parent == p:
            raise SystemExit("fatal: not inside a reporoot (no registry dir, projects/, or .reporoot-active found)")
        p = p.parent


# --- Active project ---


def active_project(root: Path) -> str | None:
    """Read .reporoot-active and return the project name, or None if no project is active.

    Validates that the named project directory exists.  If .reporoot-active names a
    project that doesn't exist in projects/, prints a warning and returns None.
    """
    active_file = root / ".reporoot-active"
    if not active_file.exists():
        return None
    name = active_file.read_text().strip()
    if not name:
        return None
    project_dir = root / "projects" / name
    if not project_dir.is_dir():
        print(f"warning: .reporoot-active names '{name}' but projects/{name}/ does not exist")
        return None
    return name


def require_active_project(root: Path) -> str:
    """Like active_project() but raises SystemExit if no project is active."""
    name = active_project(root)
    if name is None:
        raise SystemExit("fatal: no active project (run 'reporoot activate <project>')")
    return name


def active_repos_file(root: Path) -> Path:
    """Return the .repos file path for the active project."""
    name = require_active_project(root)
    return project_repos_file(root, name)


def active_lock_file(root: Path) -> Path:
    """Return the .lock.repos file path for the active project."""
    name = require_active_project(root)
    return project_lock_file(root, name)


def project_repos_file(root: Path, project: str) -> Path:
    """Return the .repos file path for a named project.

    Supports multi-segment project paths (e.g., 'chatly/web-app').
    The basename of the path is used as the file stem.
    """
    basename = Path(project).name
    return root / "projects" / project / f"{basename}.repos"


def project_lock_file(root: Path, project: str) -> Path:
    """Return the .lock.repos file path for a named project.

    Supports multi-segment project paths (e.g., 'chatly/web-app').
    The basename of the path is used as the file stem.
    """
    basename = Path(project).name
    return root / "projects" / project / f"{basename}.lock.repos"


def all_project_repos_files(root: Path) -> list[tuple[str, Path]]:
    """Recursively scan projects/ and return (project_path, repos_file) for each project.

    Project path is the relative path from projects/ (e.g., 'alpha' or 'chatly/web-app').
    Skips .lock.repos files.
    """
    projects_dir = root / "projects"
    if not projects_dir.is_dir():
        return []
    result = []
    for repos_file in sorted(projects_dir.rglob("*.repos")):
        if repos_file.name.endswith(".lock.repos"):
            continue
        # Derive project path: relative path from projects/ to the containing dir
        project_path = str(repos_file.parent.relative_to(projects_dir))
        result.append((project_path, repos_file))
    return result


def all_known_repos(root: Path) -> set[str]:
    """Return the union of all repo paths across all project .repos files."""
    known = set()
    for _name, repos_file in all_project_repos_files(root):
        known.update(read_repos(repos_file).keys())
    return known


def find_git_repos(base: Path) -> set[str]:
    """Find all git repos under a directory, returned as relative paths from root.

    ``base`` is a registry directory (e.g., root/github).  Paths are returned
    relative to ``base.parent`` (the reporoot).
    """
    root = base.parent
    repos: set[str] = set()
    for git_dir in sorted(base.rglob(".git")):
        if git_dir.is_dir():
            rel = str(git_dir.parent.relative_to(root))
            repos.add(rel)
    return repos


# --- URL helpers ---
# These delegate to reporoot.config but are kept for backward compatibility.


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL.

    Deprecated: use reporoot.config.parse_repo_url() for multi-registry support.
    """
    from reporoot.config import parse_repo_url
    _registry, owner, repo = parse_repo_url(url)
    return owner, repo


def normalize_github_url(owner: str, repo: str) -> str:
    """Canonical HTTPS URL for a GitHub repo.

    Deprecated: use reporoot.config.normalize_repo_url() for multi-registry support.
    """
    from reporoot.config import normalize_repo_url
    return normalize_repo_url("github", owner, repo)


# --- .repos file I/O ---
#
# Format (extended vcstool YAML):
#   repositories:
#     path/to/repo:
#       type: git
#       url: https://...
#       version: main
#       role: primary        # first-class field
#
# We append entries as text to preserve formatting.
# We use pyyaml for reading only.


def read_repos(path: Path) -> dict[str, dict]:
    """Read a .repos file. Returns {local_path: {type, url, version, role, ...}}."""
    data = read_repos_full(path)
    if not data or "repositories" not in data:
        return {}
    return data["repositories"] or {}


def read_repos_full(path: Path) -> dict:
    """Read a .repos file and return the entire YAML document.

    Returns the full dict including top-level keys like 'repositories'
    and 'integrations'.
    """
    import yaml

    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data or {}


def _format_entry(local_path: str, url: str, version: str, role: str | None = None, note: str | None = None) -> str:
    """Format a single .repos entry as YAML text."""
    comment = ""
    if note:
        comment = f"  # {note}"
    lines = [f"  {local_path}:{comment}"]
    lines.append(f"    type: git")
    lines.append(f"    url: {url}")
    lines.append(f"    version: {version}")
    if role:
        lines.append(f"    role: {role}")
    return "\n".join(lines) + "\n"


def append_entry(
    repos_file: Path,
    local_path: str,
    url: str,
    version: str,
    role: str | None = None,
    note: str | None = None,
) -> None:
    """Append a repo entry to a .repos file, creating it if needed."""
    if not repos_file.exists():
        repos_file.parent.mkdir(parents=True, exist_ok=True)
        repos_file.write_text("repositories:\n")

    # Check for duplicate
    existing = read_repos(repos_file)
    if local_path in existing:
        print(f"  skip {repos_file.name}: {local_path} already present")
        return

    entry = _format_entry(local_path, url, version, role, note)
    with open(repos_file, "a") as f:
        f.write(entry)
    print(f"  added to {repos_file.name}: {local_path}")
