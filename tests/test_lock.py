"""Tests for rr lock — per-project lock file generation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from reporoot.lock import run, run_all
from reporoot.workspace import read_repos


class TestLock:
    def test_generates_lock_file(self, workspace_with_project: tuple[Path, Path]):
        workspace, repo = workspace_with_project
        os.chdir(workspace)
        run()
        lock = workspace / "projects" / "test-project" / "reporoot.lock"
        assert lock.exists()
        repos = read_repos(lock)
        assert "github/test-owner/test-repo" in repos
        # Lock file should have a commit hash as version
        version = repos["github/test-owner/test-repo"]["version"]
        assert len(version) == 40

    def test_no_active_project_raises(self, workspace: Path):
        os.chdir(workspace)
        with pytest.raises(SystemExit, match="no active project"):
            run()

    def test_lock_from_workspace_cwd(self, workspace: Path, bare_repo: Path):
        """Lock infers project from CWD when inside a workspace."""
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)

        store = workspace / "github" / "test-owner" / "test-repo.git"
        store.parent.mkdir(parents=True)
        bare_repo.rename(store)

        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/test-owner/test-repo:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/test-repo.git\n"
            "    version: main\n"
        )

        # Create a workspace and cd into it
        from reporoot.workspace import create_workspace

        ws = create_workspace(workspace, "test-project", "default")
        os.chdir(ws)

        run()
        lock = project_dir / "reporoot.lock"
        assert lock.exists()
        repos = read_repos(lock)
        assert "github/test-owner/test-repo" in repos
        assert len(repos["github/test-owner/test-repo"]["version"]) == 40

    def test_lock_bare_repo(self, workspace: Path, bare_repo: Path):
        """Lock exports from bare repos when available."""
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)

        store = workspace / "github" / "test-owner" / "test-repo.git"
        store.parent.mkdir(parents=True)
        bare_repo.rename(store)

        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/test-owner/test-repo:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/test-repo.git\n"
            "    version: main\n"
        )

        (workspace / ".reporoot-active").write_text("test-project\n")
        os.chdir(workspace)

        run()
        lock = project_dir / "reporoot.lock"
        assert lock.exists()
        repos = read_repos(lock)
        assert "github/test-owner/test-repo" in repos


    def test_missing_repo_is_fatal(self, workspace: Path):
        """lock should fail when a declared repo is not cloned."""
        os.chdir(workspace)
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/test-owner/missing-repo:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/missing-repo.git\n"
            "    version: main\n"
        )
        (workspace / ".reporoot-active").write_text("test-project\n")

        with pytest.raises(SystemExit, match="could not be exported"):
            run()

        # Lock file should NOT be written
        assert not (project_dir / "reporoot.lock").exists()


class TestLockAll:
    def test_locks_all_projects(self, workspace_with_project: tuple[Path, Path]):
        workspace, repo = workspace_with_project
        os.chdir(workspace)
        run_all()
        lock = workspace / "projects" / "test-project" / "reporoot.lock"
        assert lock.exists()
        repos = read_repos(lock)
        assert "github/test-owner/test-repo" in repos

    def test_locks_bare_repos(self, workspace: Path, bare_repo: Path):
        """lock-all exports from bare repos."""
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)

        store = workspace / "github" / "test-owner" / "test-repo.git"
        store.parent.mkdir(parents=True)
        bare_repo.rename(store)

        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/test-owner/test-repo:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/test-repo.git\n"
            "    version: main\n"
        )

        os.chdir(workspace)
        run_all()
        lock = project_dir / "reporoot.lock"
        assert lock.exists()
        repos = read_repos(lock)
        assert "github/test-owner/test-repo" in repos

    def test_no_projects(self, workspace: Path, capsys):
        # Remove the projects dir contents (but keep the dir)
        os.chdir(workspace)
        run_all()
        captured = capsys.readouterr()
        assert "no projects found" in captured.out
