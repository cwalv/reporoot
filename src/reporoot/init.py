"""reporoot init — create a new project.

Usage:
  reporoot init <name>       Create projects/{name}/ with empty reporoot.yaml
"""

from __future__ import annotations

from reporoot.workspace import REPOS_FILE, find_root


def run(name: str) -> None:
    """Create a new project directory with scaffolding."""
    root = find_root()
    project_dir = root / "projects" / name

    if project_dir.exists():
        raise SystemExit(f"fatal: project directory already exists: projects/{name}/")

    project_dir.mkdir(parents=True)
    (project_dir / REPOS_FILE).write_text("repositories:\n")
    (project_dir / "docs").mkdir()

    print(f"created projects/{name}/")
    print(f"  {REPOS_FILE}")
    print(f"  docs/")
    print(f"\nnext: reporoot add <url> --project {name}")
