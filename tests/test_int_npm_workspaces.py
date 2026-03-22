"""Tests for npm-workspaces integration."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import make_repo_with_file

from reporoot.integrations.base import IntegrationContext
from reporoot.integrations.npm_workspaces import NpmWorkspaces


def _ctx(workspace: Path, repos: dict[str, dict], config: dict | None = None) -> IntegrationContext:
    return IntegrationContext(root=workspace, project="test", repos=repos, config=config or {})


class TestNpmWorkspacesActivate:
    def test_generates_package_json(self, workspace: Path):
        make_repo_with_file(workspace, "github/a/web", "package.json", '{"name": "@a/web"}')
        make_repo_with_file(workspace, "github/a/lib", "package.json", '{"name": "@a/lib"}')

        repos = {
            "github/a/web": {"type": "git", "url": "https://github.com/a/web.git", "version": "main"},
            "github/a/lib": {"type": "git", "url": "https://github.com/a/lib.git", "version": "main"},
        }

        NpmWorkspaces().activate(_ctx(workspace, repos))

        pkg = json.loads((workspace / "package.json").read_text())
        assert pkg["private"] is True
        assert pkg["workspaces"] == ["github/a/lib", "github/a/web"]

    def test_skips_repos_without_package_json(self, workspace: Path):
        make_repo_with_file(workspace, "github/a/web", "package.json", '{"name": "@a/web"}')
        repo_dir = workspace / "github" / "a" / "go-svc"
        repo_dir.mkdir(parents=True)

        repos = {
            "github/a/web": {"type": "git", "url": "https://github.com/a/web.git", "version": "main"},
            "github/a/go-svc": {"type": "git", "url": "https://github.com/a/go-svc.git", "version": "main"},
        }

        NpmWorkspaces().activate(_ctx(workspace, repos))

        pkg = json.loads((workspace / "package.json").read_text())
        assert pkg["workspaces"] == ["github/a/web"]

    def test_removes_when_no_node_repos(self, workspace: Path):
        (workspace / "package.json").write_text('{"old": true}')

        NpmWorkspaces().activate(_ctx(workspace, {}))
        assert not (workspace / "package.json").exists()

    def test_deactivate_removes_file(self, workspace: Path):
        (workspace / "package.json").write_text("{}")
        NpmWorkspaces().deactivate(workspace)
        assert not (workspace / "package.json").exists()

    def test_excludes_reference_repos(self, workspace: Path):
        make_repo_with_file(workspace, "github/a/web", "package.json", '{"name": "@a/web"}')
        make_repo_with_file(workspace, "github/a/ref", "package.json", '{"name": "@a/ref"}')

        repos = {
            "github/a/web": {"type": "git", "url": "u", "version": "main", "role": "primary"},
            "github/a/ref": {"type": "git", "url": "u", "version": "main", "role": "reference"},
        }

        NpmWorkspaces().activate(_ctx(workspace, repos))

        pkg = json.loads((workspace / "package.json").read_text())
        assert pkg["workspaces"] == ["github/a/web"]

    def test_deactivate_noop_if_missing(self, workspace: Path):
        NpmWorkspaces().deactivate(workspace)  # should not raise
