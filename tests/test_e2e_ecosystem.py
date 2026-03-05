"""Ecosystem integration e2e tests — require real tools (npm, go, uv, gita).

These tests exercise the full activate → ecosystem-tool cycle.  Each test
creates a workspace with repos containing ecosystem manifest files, runs
``reporoot activate`` via the CLI, and verifies that the ecosystem tool
produces the expected output.

Tests are skipped when the required tool is not on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Tool availability markers
# ---------------------------------------------------------------------------

has_npm = shutil.which("npm") is not None
has_go = shutil.which("go") is not None
has_uv = shutil.which("uv") is not None
has_gita = shutil.which("gita") is not None


def _make_git_repo(path: Path, files: dict[str, str] | None = None) -> None:
    """Create a minimal git repo at *path* with optional files."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    for name, content in (files or {"README.md": "hello\n"}).items():
        fp = path / name
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, check=True)


@pytest.fixture()
def eco_workspace(tmp_path: Path) -> Path:
    """Create a workspace with projects/ and github/ dirs."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "github").mkdir()
    (ws / "projects").mkdir()
    return ws


def _activate(project: str) -> None:
    """Run reporoot activate via CLI."""
    from reporoot.cli import main

    main(["activate", project])


def _setup_project(ws: Path, project: str, repos: dict[str, dict]) -> None:
    """Create project dir with reporoot.yaml and set active."""
    project_dir = ws / "projects" / project
    project_dir.mkdir(parents=True, exist_ok=True)

    lines = ["repositories:"]
    for path, info in repos.items():
        lines.append(f"  {path}:")
        lines.append(f"    type: {info.get('type', 'git')}")
        lines.append(f"    url: {info.get('url', 'https://github.com/test/repo.git')}")
        lines.append(f"    version: {info.get('version', 'main')}")
        lines.append(f"    role: {info.get('role', 'primary')}")

    (project_dir / "reporoot.yaml").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# npm workspaces
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not has_npm, reason="npm not on PATH")
class TestNpmWorkspacesE2E:
    def test_npm_install_resolves_workspaces(self, eco_workspace: Path):
        """Activate with Node repos → npm install succeeds with workspace linking."""
        ws = eco_workspace
        os.chdir(ws)

        # Create two repos with package.json
        _make_git_repo(
            ws / "github" / "test" / "lib-a",
            files={
                "package.json": json.dumps({"name": "@test/lib-a", "version": "1.0.0"}),
            },
        )
        _make_git_repo(
            ws / "github" / "test" / "app",
            files={
                "package.json": json.dumps(
                    {
                        "name": "@test/app",
                        "version": "1.0.0",
                        "dependencies": {"@test/lib-a": "*"},
                    }
                ),
            },
        )

        repos = {
            "github/test/lib-a": {"url": "https://github.com/test/lib-a.git"},
            "github/test/app": {"url": "https://github.com/test/app.git"},
        }
        _setup_project(ws, "myproject", repos)
        _activate("myproject")

        # Verify root package.json was generated
        root_pkg = json.loads((ws / "package.json").read_text())
        assert set(root_pkg["workspaces"]) == {"github/test/app", "github/test/lib-a"}

        # Verify node_modules exists (npm install ran)
        assert (ws / "node_modules").is_dir()


# ---------------------------------------------------------------------------
# go work
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not has_go, reason="go not on PATH")
class TestGoWorkE2E:
    def test_go_work_sync(self, eco_workspace: Path):
        """Activate with Go repos → go.work is generated and valid."""
        ws = eco_workspace
        os.chdir(ws)

        _make_git_repo(
            ws / "github" / "test" / "gomod",
            files={
                "go.mod": "module github.com/test/gomod\n\ngo 1.21\n",
                "main.go": "package main\n\nfunc main() {}\n",
            },
        )

        repos = {"github/test/gomod": {"url": "https://github.com/test/gomod.git"}}
        _setup_project(ws, "myproject", repos)
        _activate("myproject")

        # go.work should exist and reference the module
        go_work = ws / "go.work"
        assert go_work.exists()
        content = go_work.read_text()
        assert "github/test/gomod" in content


# ---------------------------------------------------------------------------
# uv workspace
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not has_uv, reason="uv not on PATH")
class TestUvWorkspaceE2E:
    def test_uv_sync_succeeds(self, eco_workspace: Path):
        """Activate with Python repos → root pyproject.toml + uv sync succeeds."""
        ws = eco_workspace
        os.chdir(ws)

        _make_git_repo(
            ws / "github" / "test" / "pylib",
            files={
                "pyproject.toml": (
                    '[project]\nname = "pylib"\nversion = "0.1.0"\nrequires-python = ">=3.10"\ndependencies = []\n'
                ),
            },
        )

        repos = {"github/test/pylib": {"url": "https://github.com/test/pylib.git"}}
        _setup_project(ws, "myproject", repos)
        _activate("myproject")

        # Root pyproject.toml with uv workspace should exist
        root_toml = ws / "pyproject.toml"
        assert root_toml.exists()
        content = root_toml.read_text()
        assert "github/test/pylib" in content


# ---------------------------------------------------------------------------
# gita
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not has_gita, reason="gita not on PATH")
class TestGitaE2E:
    def test_gita_repos_created(self, eco_workspace: Path):
        """Activate → .gita/ directory with repos.csv and groups.csv."""
        ws = eco_workspace
        os.chdir(ws)

        _make_git_repo(ws / "github" / "test" / "repo1")

        repos = {
            "github/test/repo1": {
                "url": "https://github.com/test/repo1.git",
                "role": "primary",
            },
        }
        _setup_project(ws, "myproject", repos)
        _activate("myproject")

        gita_dir = ws / ".gita"
        assert gita_dir.is_dir()
        assert (gita_dir / "repos.csv").exists()
        assert (gita_dir / "groups.csv").exists()

        # repos.csv should reference the repo
        repos_csv = (gita_dir / "repos.csv").read_text()
        assert "repo1" in repos_csv

        # groups.csv should have the primary group
        groups_csv = (gita_dir / "groups.csv").read_text()
        assert "primary" in groups_csv
