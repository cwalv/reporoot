"""Tests for reporoot check — multi-project convention enforcement."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from reporoot.check import run


def _make_git_repo(path: Path) -> None:
    """Create a minimal git repo at the given path."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True, check=True)
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, check=True)


def _make_bare_repo(path: Path) -> None:
    """Create a minimal bare git repo at the given path (should end in .git)."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare"], cwd=path, capture_output=True, check=True)


class TestCheck:
    def test_all_clean(self, workspace: Path, capsys):
        os.chdir(workspace)

        # Create a repo on disk (clone + bare)
        _make_git_repo(workspace / "github" / "a" / "lib")
        _make_bare_repo(workspace / "github" / "a" / "lib.git")

        # Register it in a project with role field
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/a/lib:\n"
            "    type: git\n"
            "    url: https://github.com/a/lib.git\n"
            "    version: main\n"
            "    role: primary\n"
        )

        run()
        captured = capsys.readouterr()
        assert "all checks passed" in captured.out

    def test_orphaned_clone(self, workspace: Path, capsys):
        os.chdir(workspace)

        # Repo on disk but not in any project reporoot.yaml
        _make_git_repo(workspace / "github" / "a" / "orphan")

        # Empty project
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text("repositories:\n")

        with pytest.raises(SystemExit):
            run(verbose=True)
        captured = capsys.readouterr()
        assert "orphan:" in captured.out
        assert "github/a/orphan" in captured.out

    def test_orphaned_bare_repo(self, workspace: Path, capsys):
        """A bare repo on disk not in any project is flagged as orphan-bare."""
        os.chdir(workspace)

        # Bare repo on disk but not in any project reporoot.yaml
        _make_bare_repo(workspace / "github" / "a" / "stray.git")

        # Empty project
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text("repositories:\n")

        with pytest.raises(SystemExit):
            run(verbose=True)
        captured = capsys.readouterr()
        assert "orphan-bare:" in captured.out
        assert "github/a/stray" in captured.out

    def test_dangling_ref(self, workspace: Path, capsys):
        os.chdir(workspace)

        # Project references a repo that's not on disk
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/a/missing:\n"
            "    type: git\n"
            "    url: https://github.com/a/missing.git\n"
            "    version: main\n"
            "    role: primary\n"
        )

        with pytest.raises(SystemExit):
            run(verbose=True)
        captured = capsys.readouterr()
        assert "dangling:" in captured.out
        assert "github/a/missing" in captured.out

    def test_dangling_bare_ref(self, workspace: Path, capsys):
        """A manifest entry with a clone but no bare repo is flagged as dangling-bare."""
        os.chdir(workspace)

        # Clone exists but no bare repo
        _make_git_repo(workspace / "github" / "a" / "lib")

        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/a/lib:\n"
            "    type: git\n"
            "    url: https://github.com/a/lib.git\n"
            "    version: main\n"
            "    role: primary\n"
        )

        with pytest.raises(SystemExit):
            run(verbose=True)
        captured = capsys.readouterr()
        assert "dangling-bare:" in captured.out
        assert "github/a/lib" in captured.out
        # Should NOT have a regular dangling issue (clone exists)
        assert "dangling: " not in captured.out

    def test_missing_role_field(self, workspace: Path, capsys):
        os.chdir(workspace)

        _make_git_repo(workspace / "github" / "a" / "lib")
        _make_bare_repo(workspace / "github" / "a" / "lib.git")

        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n  github/a/lib:\n    type: git\n    url: https://github.com/a/lib.git\n    version: main\n"
        )

        with pytest.raises(SystemExit):
            run(verbose=True)
        captured = capsys.readouterr()
        assert "role" in captured.out

    def test_repo_in_any_project_not_orphan(self, workspace: Path, capsys):
        """A repo in ANY project's reporoot.yaml is not an orphan, even if only in one."""
        os.chdir(workspace)

        _make_git_repo(workspace / "github" / "a" / "shared")
        _make_git_repo(workspace / "github" / "a" / "only-alpha")
        _make_bare_repo(workspace / "github" / "a" / "shared.git")
        _make_bare_repo(workspace / "github" / "a" / "only-alpha.git")

        # Project alpha has both repos
        alpha = workspace / "projects" / "alpha"
        alpha.mkdir(parents=True)
        (alpha / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/a/shared:\n"
            "    type: git\n"
            "    url: https://github.com/a/shared.git\n"
            "    version: main\n"
            "    role: primary\n"
            "  github/a/only-alpha:\n"
            "    type: git\n"
            "    url: https://github.com/a/only-alpha.git\n"
            "    version: main\n"
            "    role: primary\n"
        )

        # Project beta has only shared
        beta = workspace / "projects" / "beta"
        beta.mkdir(parents=True)
        (beta / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/a/shared:\n"
            "    type: git\n"
            "    url: https://github.com/a/shared.git\n"
            "    version: main\n"
            "    role: dependency\n"
        )

        run()
        captured = capsys.readouterr()
        assert "all checks passed" in captured.out
