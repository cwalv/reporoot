"""Tests for claude-md integration."""

from __future__ import annotations

from pathlib import Path

from reporoot.integrations.base import IntegrationContext
from reporoot.integrations.claude_md import _HEADER, ClaudeMd


def _ctx(workspace: Path, repos: dict[str, dict], project: str = "test") -> IntegrationContext:
    return IntegrationContext(root=workspace, project=project, repos=repos, config={})


class TestClaudeMdActivate:
    def test_generates_file(self, workspace: Path):
        repos = {
            "github/a/server": {
                "type": "git",
                "url": "https://github.com/a/server.git",
                "version": "main",
                "role": "primary",
            },
        }
        ClaudeMd().activate(_ctx(workspace, repos))

        claude_md = workspace / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert content.startswith(_HEADER)
        assert "Active project: **test**" in content

    def test_includes_repos(self, workspace: Path):
        repos = {
            "github/a/server": {
                "type": "git",
                "url": "https://github.com/a/server.git",
                "version": "main",
                "role": "primary",
            },
            "github/b/lib": {
                "type": "git",
                "url": "https://github.com/b/lib.git",
                "version": "main",
                "role": "dependency",
            },
        }
        ClaudeMd().activate(_ctx(workspace, repos))

        content = (workspace / "CLAUDE.md").read_text()
        assert "github/a/server" in content
        assert "github/b/lib" in content
        assert "primary" in content
        assert "dependency" in content

    def test_includes_roles_reference(self, workspace: Path):
        ClaudeMd().activate(_ctx(workspace, {}))

        content = (workspace / "CLAUDE.md").read_text()
        assert "**primary**" in content
        assert "**fork**" in content
        assert "**dependency**" in content
        assert "**reference**" in content

    def test_includes_project_directory(self, workspace: Path):
        ClaudeMd().activate(_ctx(workspace, {}, project="web-app"))

        content = (workspace / "CLAUDE.md").read_text()
        assert "projects/web-app/" in content


class TestClaudeMdDeactivate:
    def test_removes_generated_file(self, workspace: Path):
        target = workspace / "CLAUDE.md"
        target.write_text(_HEADER + "\nsome content\n")

        ClaudeMd().deactivate(workspace)
        assert not target.exists()

    def test_preserves_user_file(self, workspace: Path):
        target = workspace / "CLAUDE.md"
        target.write_text("# My custom instructions\n")

        ClaudeMd().deactivate(workspace)
        assert target.exists()  # should not be removed

    def test_noop_if_missing(self, workspace: Path):
        ClaudeMd().deactivate(workspace)  # should not raise


class TestClaudeMdCheck:
    def test_no_issues_when_present(self, workspace: Path):
        (workspace / "CLAUDE.md").write_text(_HEADER + "\ncontent\n")

        issues = ClaudeMd().check(_ctx(workspace, {}))
        assert len(issues) == 0

    def test_missing_file(self, workspace: Path):
        issues = ClaudeMd().check(_ctx(workspace, {}))
        assert len(issues) == 1
        assert "missing" in issues[0].message

    def test_non_generated_file(self, workspace: Path):
        (workspace / "CLAUDE.md").write_text("# Custom file\n")

        issues = ClaudeMd().check(_ctx(workspace, {}))
        assert len(issues) == 1
        assert "not generated" in issues[0].message
