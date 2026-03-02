"""Tests for vscode-workspace integration."""

from __future__ import annotations

import json
import os
from pathlib import Path

from reporoot.integrations.base import IntegrationContext
from reporoot.integrations.vscode_workspace import VscodeWorkspace, _EXT, _GEN_DIR


def _ctx(
    workspace: Path,
    repos: dict[str, dict],
    config: dict | None = None,
    project: str = "test",
    all_repos_on_disk: set[str] | None = None,
    all_project_paths: list[str] | None = None,
) -> IntegrationContext:
    return IntegrationContext(
        root=workspace,
        project=project,
        repos=repos,
        config=config or {},
        all_repos_on_disk=all_repos_on_disk or set(repos.keys()),
        all_project_paths=all_project_paths or [project],
    )


def _two_repos(workspace: Path) -> dict[str, dict]:
    repos = {
        "github/a/web": {"type": "git", "url": "https://github.com/a/web.git", "version": "main"},
        "github/a/lib": {"type": "git", "url": "https://github.com/a/lib.git", "version": "main"},
    }
    for repo_path in repos:
        (workspace / repo_path).mkdir(parents=True, exist_ok=True)
    return repos


def _filename(project: str = "test") -> str:
    return Path(project).name + _EXT


class TestVscodeWorkspaceActivate:
    def test_generates_in_project_dir(self, workspace: Path):
        repos = _two_repos(workspace)
        VscodeWorkspace().activate(_ctx(workspace, repos))

        canonical = workspace / "projects" / "test" / _GEN_DIR / _filename()
        assert canonical.exists()
        data = json.loads(canonical.read_text())
        assert "folders" in data

    def test_creates_symlink_at_root(self, workspace: Path):
        repos = _two_repos(workspace)
        VscodeWorkspace().activate(_ctx(workspace, repos))

        link = workspace / _filename()
        assert link.is_symlink()
        expected_target = Path("projects") / "test" / _GEN_DIR / _filename()
        assert Path(os.readlink(link)) == expected_target

    def test_project_named_file(self, workspace: Path):
        repos = _two_repos(workspace)
        VscodeWorkspace().activate(_ctx(workspace, repos, project="web-app"))

        assert (workspace / "web-app.code-workspace").is_symlink()

    def test_single_root_folder(self, workspace: Path):
        repos = _two_repos(workspace)
        VscodeWorkspace().activate(_ctx(workspace, repos))

        canonical = workspace / "projects" / "test" / _GEN_DIR / _filename()
        data = json.loads(canonical.read_text())
        assert len(data["folders"]) == 1
        assert data["folders"][0]["name"] == "test"

    def test_folder_path_relative_to_symlink(self, workspace: Path):
        """Folder path is '.' — relative to the symlink at root, not the real file."""
        repos = _two_repos(workspace)
        VscodeWorkspace().activate(_ctx(workspace, repos))

        canonical = workspace / "projects" / "test" / _GEN_DIR / _filename()
        data = json.loads(canonical.read_text())
        root_folder = data["folders"][0]
        assert root_folder["path"] == "."

    def test_files_exclude_hides_non_project_repos(self, workspace: Path):
        repos = _two_repos(workspace)
        # Simulate extra repos on disk not in active project
        all_on_disk = set(repos.keys()) | {"github/b/other", "github/c/extra"}
        ctx = _ctx(workspace, repos, all_repos_on_disk=all_on_disk)

        VscodeWorkspace().activate(ctx)

        canonical = workspace / "projects" / "test" / _GEN_DIR / _filename()
        data = json.loads(canonical.read_text())
        excludes = data["settings"]["files.exclude"]
        # Dotfiles/dirs hidden
        assert excludes[".*"] is True
        # Owners with all repos excluded are collapsed to owner level
        assert excludes["github/b"] is True
        assert excludes["github/c"] is True
        assert "github/b/other" not in excludes
        assert "github/c/extra" not in excludes
        # Active project repos not excluded
        assert "github/a/web" not in excludes
        assert "github/a/lib" not in excludes

    def test_exclude_collapses_partial_owner(self, workspace: Path):
        """When an owner has both active and excluded repos, list individually."""
        repos = _two_repos(workspace)  # github/a/web, github/a/lib active
        all_on_disk = set(repos.keys()) | {"github/a/extra"}
        ctx = _ctx(workspace, repos, all_repos_on_disk=all_on_disk)

        VscodeWorkspace().activate(ctx)

        canonical = workspace / "projects" / "test" / _GEN_DIR / _filename()
        data = json.loads(canonical.read_text())
        excludes = data["settings"]["files.exclude"]
        # Only the excluded repo listed, not the owner
        assert excludes["github/a/extra"] is True
        assert "github/a" not in excludes

    def test_exclude_collapses_registry(self, workspace: Path):
        """When all owners under a registry are collapsed, collapse to registry."""
        repos = {"gitlab/x/app": {"type": "git", "url": "u", "version": "main"}}
        (workspace / "gitlab/x/app").mkdir(parents=True)
        all_on_disk = set(repos.keys()) | {"github/b/one", "github/c/two"}
        ctx = _ctx(workspace, repos, all_repos_on_disk=all_on_disk)

        VscodeWorkspace().activate(ctx)

        canonical = workspace / "projects" / "test" / _GEN_DIR / _filename()
        data = json.loads(canonical.read_text())
        excludes = data["settings"]["files.exclude"]
        # All github owners excluded → collapsed to registry
        assert excludes["github"] is True
        assert "github/b" not in excludes
        assert "github/c" not in excludes
        # Active registry not excluded
        assert "gitlab/x/app" not in excludes

    def test_files_exclude_hides_non_active_projects(self, workspace: Path):
        repos = _two_repos(workspace)
        ctx = _ctx(
            workspace, repos,
            all_project_paths=["test", "other-project", "third"],
        )

        VscodeWorkspace().activate(ctx)

        canonical = workspace / "projects" / "test" / _GEN_DIR / _filename()
        data = json.loads(canonical.read_text())
        excludes = data["settings"]["files.exclude"]
        assert excludes["projects/other-project"] is True
        assert excludes["projects/third"] is True
        assert "projects/test" not in excludes

    def test_preserves_existing_settings(self, workspace: Path):
        repos = _two_repos(workspace)
        gen_dir = workspace / "projects" / "test" / _GEN_DIR
        gen_dir.mkdir(parents=True)
        canonical = gen_dir / _filename()
        existing = {
            "folders": [{"path": "old"}],
            "settings": {
                "editor.fontSize": 14,
                "files.exclude": {"stale/": True},
            },
            "extensions": {"recommendations": ["ms-python.python"]},
        }
        canonical.write_text(json.dumps(existing))

        VscodeWorkspace().activate(_ctx(workspace, repos))

        data = json.loads(canonical.read_text())
        # Folders replaced (single root now)
        assert len(data["folders"]) == 1
        # files.exclude replaced with current state
        assert "stale/" not in data["settings"]["files.exclude"]
        # Other settings preserved
        assert data["settings"]["editor.fontSize"] == 14
        # Extensions preserved
        assert data["extensions"] == {"recommendations": ["ms-python.python"]}

    def test_replaces_existing_file_with_symlink(self, workspace: Path):
        """If a plain file exists at root (from old behavior), replace it."""
        (workspace / _filename()).write_text("{}")
        repos = _two_repos(workspace)

        VscodeWorkspace().activate(_ctx(workspace, repos))

        link = workspace / _filename()
        assert link.is_symlink()

    def test_multi_segment_project(self, workspace: Path):
        repos = _two_repos(workspace)
        project = "org/web-app"
        VscodeWorkspace().activate(_ctx(workspace, repos, project=project))

        # File named after leaf segment
        assert (workspace / "web-app.code-workspace").is_symlink()
        canonical = workspace / "projects" / "org" / "web-app" / _GEN_DIR / "web-app.code-workspace"
        assert canonical.exists()

    def test_cleanup_old_symlinks_on_switch(self, workspace: Path):
        """Switching projects removes the old project's symlink."""
        repos = _two_repos(workspace)
        VscodeWorkspace().activate(_ctx(workspace, repos, project="alpha"))
        assert (workspace / "alpha.code-workspace").is_symlink()

        VscodeWorkspace().activate(_ctx(workspace, repos, project="beta"))
        assert not (workspace / "alpha.code-workspace").exists()
        assert (workspace / "beta.code-workspace").is_symlink()


class TestVscodeWorkspaceDeactivate:
    def test_deactivate_removes_symlink(self, workspace: Path):
        repos = _two_repos(workspace)
        VscodeWorkspace().activate(_ctx(workspace, repos))

        filename = _filename()
        canonical = workspace / "projects" / "test" / _GEN_DIR / filename
        assert canonical.exists()

        VscodeWorkspace().deactivate(workspace)

        assert not (workspace / filename).exists()
        # Canonical file preserved
        assert canonical.exists()

    def test_deactivate_noop_if_no_symlink(self, workspace: Path):
        VscodeWorkspace().deactivate(workspace)  # should not raise

    def test_deactivate_ignores_plain_file(self, workspace: Path):
        """If someone put a plain .code-workspace file at root, deactivate doesn't remove it."""
        (workspace / _filename()).write_text("{}")
        VscodeWorkspace().deactivate(workspace)
        assert (workspace / _filename()).exists()


class TestVscodeWorkspaceCheck:
    def test_check_passes_when_correct(self, workspace: Path):
        repos = _two_repos(workspace)
        ctx = _ctx(workspace, repos)
        VscodeWorkspace().activate(ctx)

        issues = VscodeWorkspace().check(ctx)
        assert issues == []

    def test_check_warns_missing_symlink(self, workspace: Path):
        repos = _two_repos(workspace)
        ctx = _ctx(workspace, repos)

        issues = VscodeWorkspace().check(ctx)
        assert len(issues) == 1
        assert "missing" in issues[0].message

    def test_check_warns_stale_symlink(self, workspace: Path):
        repos = _two_repos(workspace)
        VscodeWorkspace().activate(_ctx(workspace, repos, project="test"))

        ctx = _ctx(workspace, repos, project="other")
        issues = VscodeWorkspace().check(ctx)
        assert len(issues) == 1
        assert "missing" in issues[0].message  # other.code-workspace doesn't exist
