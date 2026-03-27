"""Tests for reporoot add — adding repos to the active project."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from reporoot.add import run
from reporoot.workspace import bare_repo_path, read_repos


class TestAddFromLocal:
    def test_add_local_repo(self, workspace_with_project: tuple[Path, Path], git_repo: Path):
        workspace, _ = workspace_with_project
        ws_dir = workspace / "projects" / "test-project" / "workspaces" / "default"
        os.chdir(ws_dir)

        # Create a second git repo to add
        second = git_repo.parent / "repo2"
        second.mkdir()

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

        # Bare clone should exist
        bare = bare_repo_path(workspace, "github/other-owner/other-repo")
        assert bare.exists()

        # Worktree should exist in the workspace
        wt = ws_dir / "github" / "other-owner" / "other-repo"
        assert wt.exists()
        assert (wt / "README.md").exists()

        # Should be in active project's reporoot.yaml
        project_repos = read_repos(workspace / "projects" / "test-project" / "reporoot.yaml")
        assert "github/other-owner/other-repo" in project_repos

    def test_add_existing_repo_skips_clone(self, workspace_with_project: tuple[Path, Path]):
        workspace, repo = workspace_with_project
        ws_dir = workspace / "projects" / "test-project" / "workspaces" / "default"
        os.chdir(ws_dir)
        # test-owner/test-repo already exists from fixture — should skip clone and register
        run(source="https://github.com/test-owner/test-repo.git", role="primary")
        project_repos = read_repos(workspace / "projects" / "test-project" / "reporoot.yaml")
        assert "github/test-owner/test-repo" in project_repos

    def test_add_requires_project_context(self, workspace: Path, git_repo: Path):
        os.chdir(workspace)
        with pytest.raises(SystemExit, match="cannot determine project"):
            run(source=str(git_repo))

    def test_add_with_project_override(self, workspace: Path, git_repo: Path):
        os.chdir(workspace)
        # Create project dir and workspace dir
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        ws_dir = workspace / "projects" / "myproject" / "workspaces" / "default"
        ws_dir.mkdir(parents=True)

        run(source=str(git_repo), project="myproject", role="primary", note="our code")

        project_repos = project_dir / "reporoot.yaml"
        assert project_repos.exists()
        repos = read_repos(project_repos)
        assert repos["github/test-owner/test-repo"]["role"] == "primary"
        assert repos["github/test-owner/test-repo"]["note"] == "our code"


class TestAddBareRepo:
    """Tests for add in workspace context (bare clone + worktree flow)."""

    def test_add_url_creates_bare_clone_and_worktree(self, workspace_with_bare_repo: tuple[Path, Path], git_repo: Path):
        root, _ = workspace_with_bare_repo
        ws_dir = root / "projects" / "test-project" / "workspaces" / "default"
        os.chdir(ws_dir)

        # Create a second git repo to add
        second = git_repo.parent / "repo2"
        second.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=second, capture_output=True, check=True)
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

        # Use the local repo as the "URL" (file:// protocol)
        run(source=str(second))

        # Bare clone should exist
        bare = bare_repo_path(root, "github/other-owner/other-repo")
        assert bare.exists()
        assert bare.name == "other-repo.git"

        # Worktree should exist in the workspace
        wt = ws_dir / "github" / "other-owner" / "other-repo"
        assert wt.exists()
        assert (wt / "README.md").exists()

        # Should be in project reporoot.yaml
        project_repos = read_repos(root / "projects" / "test-project" / "reporoot.yaml")
        assert "github/other-owner/other-repo" in project_repos

    def test_add_existing_bare_skips_clone(self, workspace_with_bare_repo: tuple[Path, Path]):
        root, bare = workspace_with_bare_repo
        ws_dir = root / "projects" / "test-project" / "workspaces" / "default"
        os.chdir(ws_dir)

        # The bare repo already exists — add should skip clone but still succeed
        # (worktree also already exists from fixture)
        run(source="https://github.com/test-owner/test-repo.git", role="primary")

        project_repos = read_repos(root / "projects" / "test-project" / "reporoot.yaml")
        assert "github/test-owner/test-repo" in project_repos

    def test_add_from_project_dir_uses_default_workspace(
        self, workspace_with_project: tuple[Path, Path], git_repo: Path
    ):
        """When in a project dir (not a workspace), add resolves to the default workspace."""
        workspace, _ = workspace_with_project
        os.chdir(workspace / "projects" / "test-project")

        # Create a second git repo to add
        second = git_repo.parent / "repo2"
        second.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=second, capture_output=True, check=True)
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

        # Bare clone should exist (not a regular clone)
        bare = bare_repo_path(workspace, "github/other-owner/other-repo")
        assert bare.exists()

        # Worktree should be in the default workspace
        ws_dir = workspace / "projects" / "test-project" / "workspaces" / "default"
        wt = ws_dir / "github" / "other-owner" / "other-repo"
        assert wt.exists()
        assert (wt / "README.md").exists()


class TestAddInvalidSource:
    def test_nonexistent_path(self, workspace_with_project: tuple[Path, Path]):
        workspace, _ = workspace_with_project
        os.chdir(workspace / "projects" / "test-project")
        with pytest.raises(SystemExit, match="not a URL or a local git repo"):
            run(source="/nonexistent/path")
