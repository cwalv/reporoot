"""Tests for reporoot remove — removing repos from the active project."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from reporoot.remove import run
from reporoot.workspace import read_repos


class TestRemove:
    def test_remove_existing_repo(self, workspace_with_project: tuple[Path, Path]):
        workspace, repo = workspace_with_project
        os.chdir(workspace)

        repos_file = workspace / "projects" / "test-project" / "test-project.repos"
        assert "github/test-owner/test-repo" in read_repos(repos_file)

        run(path="github/test-owner/test-repo")

        assert "github/test-owner/test-repo" not in read_repos(repos_file)
        # Clone should still be on disk
        assert repo.exists()

    def test_remove_with_delete(self, workspace_with_project: tuple[Path, Path]):
        workspace, repo = workspace_with_project
        os.chdir(workspace)

        assert repo.exists()
        run(path="github/test-owner/test-repo", delete=True, force=True)

        repos_file = workspace / "projects" / "test-project" / "test-project.repos"
        assert "github/test-owner/test-repo" not in read_repos(repos_file)
        assert not repo.exists()

    def test_remove_nonexistent_path(self, workspace_with_project: tuple[Path, Path]):
        workspace, _ = workspace_with_project
        os.chdir(workspace)

        with pytest.raises(SystemExit, match="not found"):
            run(path="github/no-owner/no-repo")

    def test_remove_with_project_override(self, workspace: Path):
        os.chdir(workspace)

        # Create two projects, each with a repo entry
        for name in ("alpha", "beta"):
            project_dir = workspace / "projects" / name
            project_dir.mkdir(parents=True)
            (project_dir / f"{name}.repos").write_text(
                "repositories:\n"
                "  github/test-owner/test-repo:\n"
                "    type: git\n"
                "    url: https://github.com/test-owner/test-repo.git\n"
                "    version: main\n"
                "    role: primary\n"
            )

        # Set alpha as active
        (workspace / ".reporoot-active").write_text("alpha\n")

        # Remove from beta (not the active project)
        run(path="github/test-owner/test-repo", project="beta")

        # beta should have it removed
        beta_repos = read_repos(workspace / "projects" / "beta" / "beta.repos")
        assert "github/test-owner/test-repo" not in beta_repos

        # alpha should still have it
        alpha_repos = read_repos(workspace / "projects" / "alpha" / "alpha.repos")
        assert "github/test-owner/test-repo" in alpha_repos

    def test_remove_delete_not_on_disk(
        self, workspace_with_project: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ):
        workspace, repo = workspace_with_project
        os.chdir(workspace)

        # Manually remove the clone so --delete has nothing to delete
        import shutil

        shutil.rmtree(repo)

        run(path="github/test-owner/test-repo", delete=True, force=True)

        repos_file = workspace / "projects" / "test-project" / "test-project.repos"
        assert "github/test-owner/test-repo" not in read_repos(repos_file)
        captured = capsys.readouterr()
        assert "not on disk" in captured.out
