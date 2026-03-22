"""Tests for gita integration."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from reporoot.integrations.base import IntegrationContext
from reporoot.integrations.gita import Gita


def _ctx(workspace: Path, repos: dict[str, dict], config: dict | None = None) -> IntegrationContext:
    return IntegrationContext(root=workspace, project="test", repos=repos, config=config or {})


def _make_dirs(workspace: Path, repos: dict[str, dict]) -> None:
    """Create repo directories on disk so integrations can detect them."""
    for repo_path in repos:
        (workspace / repo_path).mkdir(parents=True, exist_ok=True)


class TestGitaActivate:
    def test_generates_repos_csv(self, workspace: Path):
        repos = {
            "github/a/server": {
                "type": "git",
                "url": "https://github.com/a/server.git",
                "version": "main",
                "role": "primary",
            },
            "github/a/lib": {
                "type": "git",
                "url": "https://github.com/a/lib.git",
                "version": "main",
                "role": "dependency",
            },
        }
        _make_dirs(workspace, repos)

        Gita().activate(_ctx(workspace, repos))

        repos_csv = (workspace / "gita" / "repos.csv").read_text()
        reader = csv.reader(io.StringIO(repos_csv))
        rows = list(reader)
        # 2 repos, no header
        assert len(rows) == 2
        # Sorted by repo path
        assert rows[0][1] == "lib"  # name column
        assert rows[1][1] == "server"

    def test_generates_groups_csv(self, workspace: Path):
        repos = {
            "github/a/server": {
                "type": "git",
                "url": "https://github.com/a/server.git",
                "version": "main",
                "role": "primary",
            },
            "github/a/lib": {
                "type": "git",
                "url": "https://github.com/a/lib.git",
                "version": "main",
                "role": "dependency",
            },
        }
        _make_dirs(workspace, repos)

        Gita().activate(_ctx(workspace, repos))

        groups_csv = (workspace / "gita" / "groups.csv").read_text()
        # Colon-delimited: group:repos
        assert "primary:server" in groups_csv
        assert "dependency:lib" in groups_csv

    def test_deactivate_removes_directory(self, workspace: Path):
        gita_dir = workspace / "gita"
        gita_dir.mkdir()
        (gita_dir / "repos.csv").write_text("")
        (gita_dir / "groups.csv").write_text("")

        Gita().deactivate(workspace)
        assert not gita_dir.exists()

    def test_deactivate_noop_if_missing(self, workspace: Path):
        Gita().deactivate(workspace)  # should not raise
