"""Tests for vscode-workspace integration."""

from __future__ import annotations

import json
from pathlib import Path

from reporoot.integrations.base import IntegrationContext
from reporoot.integrations.vscode_workspace import _EXT, VscodeWorkspace


def _ctx(
    workspace: Path,
    repos: dict[str, dict],
    config: dict | None = None,
    project: str = "test",
) -> IntegrationContext:
    return IntegrationContext(
        root=workspace,
        project=project,
        repos=repos,
        config=config or {},
    )


def _ws_root(tmp_path: Path, name: str = "default") -> Path:
    """Create a root that looks like a workspace dir (under workspaces/)."""
    ws = tmp_path / "projects" / "myproj" / "workspaces" / name
    ws.mkdir(parents=True)
    return ws


def _filename(project: str = "test") -> str:
    return Path(project).name + _EXT


class TestVscodeWorkspaceActivate:
    def test_writes_file_at_root(self, workspace: Path):
        VscodeWorkspace().activate(_ctx(workspace, {}))
        target = workspace / _filename()
        assert target.is_file()
        assert not target.is_symlink()

    def test_project_named_file(self, workspace: Path):
        VscodeWorkspace().activate(_ctx(workspace, {}, project="web-app"))
        assert (workspace / "web-app.code-workspace").is_file()

    def test_multi_segment_project(self, workspace: Path):
        VscodeWorkspace().activate(_ctx(workspace, {}, project="org/web-app"))
        assert (workspace / "web-app.code-workspace").is_file()

    def test_single_root_folder(self, workspace: Path):
        VscodeWorkspace().activate(_ctx(workspace, {}))
        data = json.loads((workspace / _filename()).read_text())
        assert len(data["folders"]) == 1
        assert data["folders"][0]["path"] == "."

    def test_folder_name_uses_workspace_name(self, tmp_path: Path):
        ws = _ws_root(tmp_path, "dev")
        VscodeWorkspace().activate(_ctx(ws, {}, project="myproj"))
        data = json.loads((ws / "myproj.code-workspace").read_text())
        assert data["folders"][0]["name"] == "workspace (dev)"

    def test_folder_name_falls_back_to_project(self, workspace: Path):
        # workspace fixture is not under a workspaces/ dir
        VscodeWorkspace().activate(_ctx(workspace, {}, project="myproj"))
        data = json.loads((workspace / "myproj.code-workspace").read_text())
        assert data["folders"][0]["name"] == "workspace (myproj)"

    def test_git_settings_injected(self, workspace: Path):
        VscodeWorkspace().activate(_ctx(workspace, {}))
        data = json.loads((workspace / _filename()).read_text())
        settings = data["settings"]
        assert settings["git.autoRepositoryDetection"] == "subFolders"
        assert settings["git.repositoryScanMaxDepth"] == 3

    def test_preserves_existing_user_settings(self, workspace: Path):
        existing = {
            "folders": [{"path": "old"}],
            "settings": {"editor.fontSize": 14},
            "extensions": {"recommendations": ["ms-python.python"]},
        }
        (workspace / _filename()).write_text(json.dumps(existing))

        VscodeWorkspace().activate(_ctx(workspace, {}))

        data = json.loads((workspace / _filename()).read_text())
        assert data["settings"]["editor.fontSize"] == 14
        assert data["extensions"] == {"recommendations": ["ms-python.python"]}
        assert len(data["folders"]) == 1

    def test_replaces_existing_symlink_with_file(self, workspace: Path):
        link = workspace / _filename()
        target = workspace / "somewhere.code-workspace"
        target.write_text("{}")
        link.symlink_to(target.name)
        assert link.is_symlink()

        VscodeWorkspace().activate(_ctx(workspace, {}))

        assert (workspace / _filename()).is_file()
        assert not (workspace / _filename()).is_symlink()


class TestVscodeWorkspaceDeactivate:
    def test_removes_code_workspace_file(self, workspace: Path):
        VscodeWorkspace().activate(_ctx(workspace, {}))
        assert (workspace / _filename()).exists()

        VscodeWorkspace().deactivate(workspace)
        assert not (workspace / _filename()).exists()

    def test_removes_legacy_symlink(self, workspace: Path):
        link = workspace / _filename()
        target = workspace / "somewhere"
        target.write_text("{}")
        link.symlink_to(target.name)

        VscodeWorkspace().deactivate(workspace)
        assert not link.exists()

    def test_noop_if_no_files(self, workspace: Path):
        VscodeWorkspace().deactivate(workspace)  # should not raise


class TestVscodeWorkspaceCheck:
    def test_passes_when_file_exists(self, workspace: Path):
        VscodeWorkspace().activate(_ctx(workspace, {}))
        issues = VscodeWorkspace().check(_ctx(workspace, {}))
        assert issues == []

    def test_warns_missing_file(self, workspace: Path):
        issues = VscodeWorkspace().check(_ctx(workspace, {}))
        assert len(issues) == 1
        assert "missing" in issues[0].message

    def test_warns_if_symlink_instead_of_file(self, workspace: Path):
        link = workspace / _filename()
        target = workspace / "real.code-workspace"
        target.write_text("{}")
        link.symlink_to(target.name)

        issues = VscodeWorkspace().check(_ctx(workspace, {}))
        assert len(issues) == 1
        assert "missing" in issues[0].message
