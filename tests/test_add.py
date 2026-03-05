"""Tests for reporoot add — adding repos to the active project."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from reporoot.add import run
from reporoot.workspace import read_repos


class TestAddFromLocal:
    def test_add_local_repo(self, workspace_with_project: tuple[Path, Path], git_repo: Path):
        workspace, _ = workspace_with_project
        os.chdir(workspace)

        # Create a second git repo to add
        second = git_repo.parent / "repo2"
        second.mkdir()
        import subprocess

        subprocess.run(["git", "init"], cwd=second, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=second, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=second, capture_output=True, check=True)
        (second / "README.md").write_text("hello\n")
        subprocess.run(["git", "add", "."], cwd=second, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=second, capture_output=True, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/other-owner/other-repo.git"],
            cwd=second,
            capture_output=True,
            check=True,
        )

        run(source=str(second))
        target = workspace / "github" / "other-owner" / "other-repo"
        assert target.exists()
        assert (target / "README.md").exists()

        # Should be in active project's reporoot.yaml
        project_repos = read_repos(workspace / "projects" / "test-project" / "reporoot.yaml")
        assert "github/other-owner/other-repo" in project_repos

    def test_add_existing_repo_skips_clone(self, workspace_with_project: tuple[Path, Path]):
        workspace, repo = workspace_with_project
        os.chdir(workspace)
        # test-owner/test-repo already exists from fixture — should skip clone and register
        run(source="https://github.com/test-owner/test-repo.git", role="primary")
        project_repos = read_repos(workspace / "projects" / "test-project" / "reporoot.yaml")
        assert "github/test-owner/test-repo" in project_repos

    def test_add_requires_active_project(self, workspace: Path, git_repo: Path):
        os.chdir(workspace)
        with pytest.raises(SystemExit, match="no active project"):
            run(source=str(git_repo))

    def test_add_with_project_override(self, workspace: Path, git_repo: Path):
        os.chdir(workspace)
        # Create project dir
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)

        run(source=str(git_repo), project="myproject", role="primary", note="our code")

        project_repos = project_dir / "reporoot.yaml"
        assert project_repos.exists()
        repos = read_repos(project_repos)
        assert repos["github/test-owner/test-repo"]["role"] == "primary"
        content = project_repos.read_text()
        assert "# our code" in content


class TestAddInvalidSource:
    def test_nonexistent_path(self, workspace_with_project: tuple[Path, Path]):
        workspace, _ = workspace_with_project
        os.chdir(workspace)
        with pytest.raises(SystemExit, match="not a URL or a local git repo"):
            run(source="/nonexistent/path")
