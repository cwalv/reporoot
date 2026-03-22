"""reporoot utilities: finding the root, reading/writing reporoot.yaml, workspace management."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

REPOS_FILE = "reporoot.yaml"
LOCK_FILE = "reporoot.lock"


def _is_workspace_dir(p: Path) -> bool:
    """Check if p is a workspace directory (inside projects/*/workspaces/).

    Workspace dirs mirror the registry layout (e.g., contain github/) but
    are not reporoot roots.  This prevents find_root from stopping early.
    """
    if p.parent.name != "workspaces":
        return False
    ancestor = p.parent.parent
    while ancestor != ancestor.parent:
        if ancestor.name == "projects":
            return True
        ancestor = ancestor.parent
    return False


def find_root(start: Path | None = None) -> Path:
    """Walk up from start (default: cwd) looking for a reporoot.

    A reporoot is identified by having a projects/ directory, an .reporoot-active
    file, or any known registry directory (github/, gitlab/, etc.).

    Skips workspace directories that mirror the registry layout to avoid
    false matches inside projects/{name}/workspaces/{ws}/.
    """
    from reporoot.config import registry_names

    p = (start or Path.cwd()).resolve()
    names = registry_names()
    while True:
        if (p / "projects").is_dir() or (p / ".reporoot-active").exists():
            return p
        if not _is_workspace_dir(p):
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


def project_fetch_source(root: Path, project: str) -> str | None:
    """Derive the fetch source shorthand for a project (e.g. 'cwalv/agent-relay').

    Reads the project repo's git remote URL and converts it to the shortest
    shorthand form suitable for ``reporoot fetch <source>``.
    Returns None if the project dir has no git remote or URL can't be parsed.
    """
    from reporoot.config import parse_repo_url
    from reporoot.git import remote_url

    project_dir = root / "projects" / project
    if not project_dir.is_dir():
        return None
    try:
        url = remote_url(project_dir)
    except Exception:
        return None
    try:
        registry, owner, repo = parse_repo_url(url)
    except ValueError:
        return None
    if registry == "github":
        return f"{owner}/{repo}"
    return f"{registry}/{owner}/{repo}"


def require_active_project(root: Path) -> str:
    """Like active_project() but raises SystemExit if no project is active."""
    name = active_project(root)
    if name is None:
        raise SystemExit("fatal: no active project (run 'reporoot activate <project>')")
    return name


def active_repos_file(root: Path) -> Path:
    """Return the reporoot.yaml path for the active project."""
    name = require_active_project(root)
    return project_repos_file(root, name)


def active_lock_file(root: Path) -> Path:
    """Return the reporoot.lock path for the active project."""
    name = require_active_project(root)
    return project_lock_file(root, name)


# --- Workspace context ---


@dataclass
class WorkspaceContext:
    """Result of inferring context from the current working directory."""

    root: Path
    project: str | None
    workspace: str | None


def infer_context(cwd: Path | None = None) -> WorkspaceContext:
    """Infer root, project, and workspace from the current working directory.

    Resolution order:
    1. If CWD is under projects/{project}/workspaces/{name}/, extract both.
    2. If CWD is under projects/{project}/, extract the project.
    3. Fall back to .reporoot-active for the project.
    """
    root = find_root(cwd)
    resolved = (cwd or Path.cwd()).resolve()

    projects_dir = root / "projects"
    try:
        rel = resolved.relative_to(projects_dir)
    except ValueError:
        return WorkspaceContext(root=root, project=active_project(root), workspace=None)

    parts = rel.parts
    if not parts:
        return WorkspaceContext(root=root, project=None, workspace=None)

    # Look for "workspaces" in path segments
    if "workspaces" in parts:
        ws_idx = parts.index("workspaces")
        project = str(Path(*parts[:ws_idx])) if ws_idx > 0 else None
        workspace = parts[ws_idx + 1] if ws_idx + 1 < len(parts) else None
        return WorkspaceContext(root=root, project=project, workspace=workspace)

    # Under projects/ but not in a workspace — find project by reporoot.yaml
    p = resolved
    while p != projects_dir:
        if (p / REPOS_FILE).exists():
            project = str(p.relative_to(projects_dir))
            return WorkspaceContext(root=root, project=project, workspace=None)
        if p.parent == p:
            break
        p = p.parent

    # Best guess: first path segment as project name
    return WorkspaceContext(root=root, project=parts[0], workspace=None)


# --- Project / workspace paths ---


def project_repos_file(root: Path, project: str) -> Path:
    """Return the reporoot.yaml path for a named project."""
    return root / "projects" / project / REPOS_FILE


def project_lock_file(root: Path, project: str) -> Path:
    """Return the reporoot.lock path for a named project."""
    return root / "projects" / project / LOCK_FILE


def workspace_dir(root: Path, project: str, name: str = "default") -> Path:
    """Return the workspace directory path."""
    return root / "projects" / project / "workspaces" / name


def bare_repo_path(root: Path, repo_path: str) -> Path:
    """Convert a logical repo path to its bare repo location.

    e.g., 'github/owner/repo' -> root/github/owner/repo.git
    """
    p = Path(repo_path)
    return root / p.parent / f"{p.name}.git"


def list_workspaces(root: Path, project: str) -> list[str]:
    """List workspace names for a project."""
    ws_parent = root / "projects" / project / "workspaces"
    if not ws_parent.is_dir():
        return []
    return sorted(d.name for d in ws_parent.iterdir() if d.is_dir())


# --- Workspace lifecycle ---


def create_workspace(root: Path, project: str, name: str = "default") -> Path:
    """Create a workspace with worktrees for all project repos.

    Creates the workspace directory and git worktrees from bare repos for
    each repo in the project manifest.  Per-workspace branch naming:
    {name}/{version} tracking origin/{version}.

    Returns the workspace directory path.
    """
    from reporoot.git import run_git, worktree_add

    ws = workspace_dir(root, project, name)
    if ws.exists():
        raise SystemExit(f"fatal: workspace '{name}' already exists for project '{project}'")

    repos_file = project_repos_file(root, project)
    if not repos_file.exists():
        raise SystemExit(f"fatal: no {REPOS_FILE} found in projects/{project}/")

    repos = read_repos(repos_file)
    ws.mkdir(parents=True)

    for repo_path, repo_info in repos.items():
        bare = bare_repo_path(root, repo_path)
        if not bare.exists():
            raise SystemExit(f"fatal: bare repo not found: {bare}\nhint: run 'reporoot fetch' to create bare clones")

        wt_dest = ws / repo_path
        wt_dest.parent.mkdir(parents=True, exist_ok=True)

        version = repo_info.get("version", "main")
        branch = f"{name}/{version}"
        track = f"origin/{version}"
        worktree_add(bare, wt_dest, branch, track=track)
        # Set push.default=upstream so `git push` maps the workspace branch
        # (e.g. default/main) to its tracked upstream (origin/main) automatically.
        run_git("-C", str(wt_dest), "config", "push.default", "upstream")
        print(f"  worktree: {repo_path} ({branch} -> {track})")

    return ws


def delete_workspace(root: Path, project: str, name: str) -> None:
    """Delete a workspace: remove worktrees, then remove the directory."""
    from reporoot.git import worktree_remove

    ws = workspace_dir(root, project, name)
    if not ws.exists():
        raise SystemExit(f"fatal: workspace '{name}' not found for project '{project}'")

    repos = read_repos(project_repos_file(root, project))
    for repo_path in repos:
        wt_path = ws / repo_path
        if wt_path.exists():
            bare = bare_repo_path(root, repo_path)
            worktree_remove(bare, wt_path, force=True)
            print(f"  removed worktree: {repo_path}")

    shutil.rmtree(ws)
    print(f"  deleted workspace: {name}")


def sync_workspace(root: Path, project: str, name: str) -> None:
    """Reconcile workspace worktrees with the project manifest.

    Adds worktrees for repos in the manifest that are missing from the workspace.
    """
    from reporoot.git import worktree_add

    ws = workspace_dir(root, project, name)
    if not ws.exists():
        raise SystemExit(f"fatal: workspace '{name}' not found for project '{project}'")

    repos = read_repos(project_repos_file(root, project))

    added = 0
    for repo_path, repo_info in repos.items():
        wt_dest = ws / repo_path
        if not wt_dest.exists():
            bare = bare_repo_path(root, repo_path)
            if not bare.exists():
                print(f"  warning: bare repo not found: {bare}")
                continue
            version = repo_info.get("version", "main")
            branch = f"{name}/{version}"
            track = f"origin/{version}"
            wt_dest.parent.mkdir(parents=True, exist_ok=True)
            worktree_add(bare, wt_dest, branch, track=track)
            print(f"  added: {repo_path}")
            added += 1

    if added == 0:
        print("  workspace in sync")


def all_project_repos_files(root: Path) -> list[tuple[str, Path]]:
    """Recursively scan projects/ and return (project_path, repos_file) for each project.

    Project path is the relative path from projects/ (e.g., 'alpha' or 'chatly/web-app').
    """
    projects_dir = root / "projects"
    if not projects_dir.is_dir():
        return []
    result = []
    for repos_file in sorted(projects_dir.rglob(REPOS_FILE)):
        project_path = str(repos_file.parent.relative_to(projects_dir))
        result.append((project_path, repos_file))
    return result


def all_known_repos(root: Path) -> set[str]:
    """Return the union of all repo paths across all project reporoot.yaml files."""
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


# --- reporoot.yaml / reporoot.lock I/O ---
#
# Format (YAML):
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
    """Read a reporoot.yaml/lock file. Returns {local_path: {type, url, version, role, ...}}."""
    data = read_repos_full(path)
    if not data or "repositories" not in data:
        return {}
    return data["repositories"] or {}


def read_repos_full(path: Path) -> dict:
    """Read a reporoot.yaml file and return the entire YAML document.

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
    """Format a single reporoot.yaml entry as YAML text."""
    comment = ""
    if note:
        comment = f"  # {note}"
    lines = [f"  {local_path}:{comment}"]
    lines.append("    type: git")
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
    """Append a repo entry to a reporoot.yaml file, creating it if needed."""
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


def remove_entry(repos_file: Path, local_path: str) -> None:
    """Remove a repo entry from a reporoot.yaml file.

    Reads the full YAML, removes the key from ``repositories``, and writes back.
    Raises SystemExit if the path is not found.
    """
    import yaml

    data = read_repos_full(repos_file)
    repos = data.get("repositories") or {}
    if local_path not in repos:
        raise SystemExit(f"fatal: {local_path} not found in {repos_file.name}")
    del repos[local_path]
    with open(repos_file, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"  removed from {repos_file.name}: {local_path}")
