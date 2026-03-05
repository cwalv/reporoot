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


class TestLockAll:
    def test_locks_all_projects(self, workspace_with_project: tuple[Path, Path]):
        workspace, repo = workspace_with_project
        os.chdir(workspace)
        run_all()
        lock = workspace / "projects" / "test-project" / "reporoot.lock"
        assert lock.exists()
        repos = read_repos(lock)
        assert "github/test-owner/test-repo" in repos

    def test_no_projects(self, workspace: Path, capsys):
        # Remove the projects dir contents (but keep the dir)
        os.chdir(workspace)
        run_all()
        captured = capsys.readouterr()
        assert "no projects found" in captured.out
