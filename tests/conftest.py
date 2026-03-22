"""Shared fixtures for reporoot tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a bare-minimum git repo with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/test-owner/test-repo.git"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    return repo


@pytest.fixture
def bare_repo(git_repo: Path, tmp_path: Path) -> Path:
    """Create a bare clone from git_repo with remote-tracking refs."""
    bare = tmp_path / "test-repo.git"
    subprocess.run(
        ["git", "clone", "--bare", str(git_repo), str(bare)],
        capture_output=True,
        check=True,
    )
    # Reconfigure fetch refspec so origin/* tracking branches exist
    subprocess.run(
        ["git", "-C", str(bare), "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(bare), "fetch", "origin"],
        capture_output=True,
        check=True,
    )
    return bare


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a minimal reporoot with github/ and projects/ dirs."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "github").mkdir()
    (ws / "projects").mkdir()
    return ws


@pytest.fixture
def workspace_with_project(workspace: Path, git_repo: Path) -> tuple[Path, Path]:
    """Workspace with an active project and one git repo registered in it."""
    # Create project directory with reporoot.yaml file
    project_dir = workspace / "projects" / "test-project"
    project_dir.mkdir(parents=True)

    # Clone the git_repo into the workspace
    target = workspace / "github" / "test-owner" / "test-repo"
    target.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--local", str(git_repo), str(target)],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(target), "remote", "set-url", "origin", "https://github.com/test-owner/test-repo.git"],
        capture_output=True,
        check=True,
    )

    # Register in project reporoot.yaml file
    (project_dir / "reporoot.yaml").write_text(
        "repositories:\n"
        "  github/test-owner/test-repo:\n"
        "    type: git\n"
        "    url: https://github.com/test-owner/test-repo.git\n"
        "    version: main\n"
        "    role: primary\n"
    )

    # Set active project
    (workspace / ".reporoot-active").write_text("test-project\n")

    return workspace, target


def make_repo_with_file(workspace: Path, repo_path: str, filename: str, content: str = "") -> Path:
    """Create a directory at repo_path with the given file."""
    repo_dir = workspace / repo_path
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / filename).write_text(content or "{}")
    return repo_dir
