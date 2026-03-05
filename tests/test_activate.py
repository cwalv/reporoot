"""Tests for reporoot activate/deactivate commands and integration registry dispatch."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import make_repo_with_file

from reporoot.activate import deactivate, run
from reporoot.integrations.registry import run_activate, run_deactivate


class TestActivate:
    def test_sets_rr_active(self, workspace: Path):
        os.chdir(workspace)
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text("repositories:\n")

        run(project="myproject")

        active = (workspace / ".reporoot-active").read_text().strip()
        assert active == "myproject"

    def test_deactivate(self, workspace: Path):
        os.chdir(workspace)
        (workspace / ".reporoot-active").write_text("something\n")
        (workspace / "package.json").write_text("{}")
        (workspace / "go.work").write_text("go 1.21")

        deactivate()

        assert not (workspace / ".reporoot-active").exists()
        assert not (workspace / "package.json").exists()
        assert not (workspace / "go.work").exists()

    def test_activate_generates_ecosystem_files(self, workspace: Path):
        os.chdir(workspace)
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/a/svc:\n"
            "    type: git\n"
            "    url: https://github.com/a/svc.git\n"
            "    version: main\n"
            "    role: primary\n"
        )
        make_repo_with_file(
            workspace,
            "github/a/svc",
            "pyproject.toml",
            '[project]\nname = "svc"\nversion = "0.1.0"\n',
        )

        run(project="myproject")

        assert (workspace / ".reporoot-active").read_text().strip() == "myproject"
        assert (workspace / "pyproject.toml").exists()
        assert "[tool.uv.workspace]" in (workspace / "pyproject.toml").read_text()
        assert (workspace / "myproject.code-workspace").is_symlink()

    def test_switching_project_cleans_stale_files(self, workspace: Path):
        os.chdir(workspace)

        # First project has a Python repo
        proj_a = workspace / "projects" / "proj-a"
        proj_a.mkdir(parents=True)
        (proj_a / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/a/svc:\n"
            "    type: git\n"
            "    url: https://github.com/a/svc.git\n"
            "    version: main\n"
            "    role: primary\n"
        )
        make_repo_with_file(
            workspace,
            "github/a/svc",
            "pyproject.toml",
            '[project]\nname = "svc"\nversion = "0.1.0"\n',
        )

        run(project="proj-a")
        assert (workspace / "pyproject.toml").exists()

        # Second project has no Python repos
        proj_b = workspace / "projects" / "proj-b"
        proj_b.mkdir(parents=True)
        (proj_b / "reporoot.yaml").write_text("repositories:\n")

        run(project="proj-b")
        assert not (workspace / "pyproject.toml").exists()

    def test_hard_reset_with_force(self, workspace: Path):
        os.chdir(workspace)
        (workspace / ".reporoot-active").write_text("something\n")
        # Integration-managed files
        (workspace / "package.json").write_text("{}")
        (workspace / "go.work").write_text("go 1.21")
        # Tool state (not managed by integrations)
        (workspace / "node_modules").mkdir()
        (workspace / "node_modules" / "foo.js").write_text("x")
        (workspace / ".venv").mkdir()  # dotdir — should be skipped

        deactivate(hard=True, force=True)

        assert not (workspace / ".reporoot-active").exists()
        assert not (workspace / "package.json").exists()
        assert not (workspace / "go.work").exists()
        assert not (workspace / "node_modules").exists()
        # dotdirs preserved
        assert (workspace / ".venv").exists()
        # Registry dirs preserved
        assert (workspace / "github").is_dir()

    def test_hard_reset_keeps_registry_and_projects(self, workspace: Path):
        os.chdir(workspace)
        # workspace fixture creates github/ and projects/ already
        (workspace / "stale_file.txt").write_text("leftover")
        (workspace / "some_dir").mkdir()
        (workspace / "some_dir" / "child").write_text("x")

        deactivate(hard=True, force=True)

        assert (workspace / "github").is_dir()
        assert (workspace / "projects").is_dir()
        assert not (workspace / "stale_file.txt").exists()
        assert not (workspace / "some_dir").exists()

    def test_hard_reset_interactive_confirm(self, workspace: Path):
        os.chdir(workspace)
        (workspace / "aaa_remove_me").mkdir()
        (workspace / "zzz_keep_me.txt").write_text("x")

        # Sorted order: aaa_remove_me, zzz_keep_me.txt
        # Say "y" to first, "n" to second
        responses = iter([True, False])
        with patch("reporoot.activate._confirm", side_effect=lambda prompt: next(responses)):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                deactivate(hard=True, force=False)

        assert not (workspace / "aaa_remove_me").exists()
        assert (workspace / "zzz_keep_me.txt").exists()

    def test_hard_reset_nothing_to_remove(self, workspace: Path):
        os.chdir(workspace)
        # Only github/ and projects/ exist — nothing to remove
        deactivate(hard=True, force=True)
        # Should not raise, just print "nothing extra to remove"

    def test_invalid_project_raises(self, workspace: Path):
        os.chdir(workspace)
        with pytest.raises(SystemExit, match="no reporoot.yaml"):
            run(project="myproject")


class TestRegistryDispatch:
    """Tests for the integration registry's activate/deactivate dispatch."""

    def test_dispatches_to_all_enabled(self, workspace: Path):
        make_repo_with_file(workspace, "github/a/web", "package.json", '{"name": "@a/web"}')
        make_repo_with_file(workspace, "github/a/go-svc", "go.mod", "module github.com/a/go-svc")

        repos = {
            "github/a/web": {"type": "git", "url": "https://github.com/a/web.git", "version": "main"},
            "github/a/go-svc": {"type": "git", "url": "https://github.com/a/go-svc.git", "version": "main"},
        }

        ran = run_activate(workspace, "myproject", repos, {})
        assert "npm-workspaces" in ran
        assert "go-work" in ran
        assert "gita" in ran
        assert "vscode-workspace" in ran
        assert "uv-workspace" in ran

    def test_disable_via_config(self, workspace: Path):
        make_repo_with_file(workspace, "github/a/web", "package.json", '{"name": "@a/web"}')

        repos = {
            "github/a/web": {"type": "git", "url": "https://github.com/a/web.git", "version": "main"},
        }

        ran = run_activate(workspace, "myproject", repos, {"npm-workspaces": {"enabled": False}})
        assert "npm-workspaces" not in ran
        assert not (workspace / "package.json").exists()

    def test_no_ecosystem_files_when_no_manifests(self, workspace: Path):
        repo_dir = workspace / "github" / "a" / "docs"
        repo_dir.mkdir(parents=True)

        repos = {
            "github/a/docs": {"type": "git", "url": "https://github.com/a/docs.git", "version": "main"},
        }

        run_activate(workspace, "myproject", repos, {})
        assert not (workspace / "package.json").exists()
        assert not (workspace / "go.work").exists()
        assert not (workspace / "pyproject.toml").exists()

    def test_deactivate_removes_all(self, workspace: Path):
        (workspace / "package.json").write_text("{}")
        (workspace / "go.work").write_text("go 1.21")
        (workspace / "pyproject.toml").write_text("# Generated by reporoot\n")
        (workspace / ".gita").mkdir()
        (workspace / ".gita" / "repos.csv").write_text("")
        # vscode-workspace deactivate only removes .code-workspace symlinks
        # that point into .reporoot-derived/
        ws_target = workspace / "projects" / "test" / ".reporoot-derived" / "test.code-workspace"
        ws_target.parent.mkdir(parents=True)
        ws_target.write_text("{}")
        (workspace / "test.code-workspace").symlink_to(ws_target.relative_to(workspace))

        run_deactivate(workspace)

        assert not (workspace / "package.json").exists()
        assert not (workspace / "go.work").exists()
        assert not (workspace / "pyproject.toml").exists()
        assert not (workspace / ".gita").exists()
        assert not (workspace / "test.code-workspace").is_symlink()

    def test_deactivate_noop_if_no_files(self, workspace: Path):
        run_deactivate(workspace)  # should not raise
