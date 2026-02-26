"""Tests for go-work integration."""

from __future__ import annotations

from pathlib import Path

from conftest import make_repo_with_file
from reporoot.integrations.base import IntegrationContext
from reporoot.integrations.go_work import GoWork


def _ctx(workspace: Path, repos: dict[str, dict], config: dict | None = None) -> IntegrationContext:
    return IntegrationContext(root=workspace, project="test", repos=repos, config=config or {})


class TestGoWorkActivate:
    def test_generates_go_work(self, workspace: Path):
        make_repo_with_file(workspace, "github/a/svc", "go.mod", "module github.com/a/svc")
        make_repo_with_file(workspace, "github/a/lib", "go.mod", "module github.com/a/lib")

        repos = {
            "github/a/svc": {"type": "git", "url": "https://github.com/a/svc.git", "version": "main"},
            "github/a/lib": {"type": "git", "url": "https://github.com/a/lib.git", "version": "main"},
        }

        GoWork().activate(_ctx(workspace, repos))

        go_work = (workspace / "go.work").read_text()
        assert "go 1.21" in go_work
        assert "./github/a/lib" in go_work
        assert "./github/a/svc" in go_work

    def test_skips_repos_without_go_mod(self, workspace: Path):
        make_repo_with_file(workspace, "github/a/svc", "go.mod", "module github.com/a/svc")
        repo_dir = workspace / "github" / "a" / "web"
        repo_dir.mkdir(parents=True)

        repos = {
            "github/a/svc": {"type": "git", "url": "https://github.com/a/svc.git", "version": "main"},
            "github/a/web": {"type": "git", "url": "https://github.com/a/web.git", "version": "main"},
        }

        GoWork().activate(_ctx(workspace, repos))

        go_work = (workspace / "go.work").read_text()
        assert "./github/a/svc" in go_work
        assert "web" not in go_work

    def test_removes_when_no_go_repos(self, workspace: Path):
        (workspace / "go.work").write_text("go 1.21")

        GoWork().activate(_ctx(workspace, {}))
        assert not (workspace / "go.work").exists()

    def test_deactivate_removes_file(self, workspace: Path):
        (workspace / "go.work").write_text("go 1.21")
        GoWork().deactivate(workspace)
        assert not (workspace / "go.work").exists()

    def test_deactivate_noop_if_missing(self, workspace: Path):
        GoWork().deactivate(workspace)  # should not raise
