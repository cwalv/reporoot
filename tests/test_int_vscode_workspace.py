"""Tests for vscode-workspace integration."""

from __future__ import annotations

import json
from pathlib import Path

from reporoot.integrations.base import IntegrationContext
from reporoot.integrations.vscode_workspace import VscodeWorkspace


def _ctx(workspace: Path, repos: dict[str, dict], config: dict | None = None) -> IntegrationContext:
    return IntegrationContext(root=workspace, project="test", repos=repos, config=config or {})


class TestVscodeWorkspaceActivate:
    def test_generates_code_workspace(self, workspace: Path):
        repos = {
            "github/a/web": {"type": "git", "url": "https://github.com/a/web.git", "version": "main"},
            "github/a/lib": {"type": "git", "url": "https://github.com/a/lib.git", "version": "main"},
        }
        for repo_path in repos:
            (workspace / repo_path).mkdir(parents=True, exist_ok=True)

        VscodeWorkspace().activate(_ctx(workspace, repos))

        ws_file = workspace / "reporoot.code-workspace"
        assert ws_file.exists()
        data = json.loads(ws_file.read_text())
        paths = [f["path"] for f in data["folders"]]
        assert "." in paths
        assert "github/a/lib" in paths
        assert "github/a/web" in paths

    def test_deactivate_removes_file(self, workspace: Path):
        (workspace / "reporoot.code-workspace").write_text("{}")
        VscodeWorkspace().deactivate(workspace)
        assert not (workspace / "reporoot.code-workspace").exists()

    def test_deactivate_noop_if_missing(self, workspace: Path):
        VscodeWorkspace().deactivate(workspace)  # should not raise
