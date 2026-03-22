"""vscode-workspace integration — generate .code-workspace file."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from reporoot.integrations.base import IntegrationContext, Issue

_EXT = ".code-workspace"
_GEN_DIR = ".reporoot-derived"


def _workspace_filename(project: str) -> str:
    """Derive workspace filename from project name (uses leaf segment)."""
    return Path(project).name + _EXT


def _collapse_excludes(excluded_repos: set[str], all_repos_on_disk: set[str]) -> set[str]:
    """Collapse exclude paths up the directory hierarchy.

    If all repos under an owner (registry/owner) are excluded, replace them
    with the owner path.  Then if all owners under a registry are excluded,
    replace them with the registry path.
    """
    # Group all on-disk repos by owner and registry.
    repos_by_owner: dict[str, set[str]] = defaultdict(set)
    for repo in all_repos_on_disk:
        parts = repo.split("/")
        owner = "/".join(parts[:2])
        repos_by_owner[owner].add(repo)

    # Collapse owners: if every repo under an owner is excluded, use the owner.
    collapsed: set[str] = set()
    collapsed_owners: set[str] = set()
    for owner, repos in repos_by_owner.items():
        if repos <= excluded_repos:
            collapsed.add(owner)
            collapsed_owners.add(owner)
        else:
            collapsed.update(repos & excluded_repos)

    # Collapse registries: if every owner under a registry is collapsed,
    # use the registry.
    owners_by_registry: dict[str, set[str]] = defaultdict(set)
    for owner in repos_by_owner:
        registry = owner.split("/")[0]
        owners_by_registry[registry].add(owner)

    for registry, owners in owners_by_registry.items():
        if owners <= collapsed_owners:
            collapsed -= owners
            collapsed.add(registry)

    return collapsed


class VscodeWorkspace:
    name = "vscode-workspace"
    default_enabled = True

    def activate(self, ctx: IntegrationContext) -> None:
        filename = _workspace_filename(ctx.project)

        if ctx.is_workspace_root:
            # Workspace dir: only project repos exist, no need for
            # symlink indirection or files.exclude filtering.
            target = ctx.root / filename

            folders: list[dict[str, str]] = [
                {"path": ".", "name": ctx.project},
            ]

            workspace: dict[str, Any]
            if target.exists() and not target.is_symlink():
                workspace = json.loads(target.read_text())
            else:
                workspace = {}
            workspace["folders"] = folders

            target.write_text(json.dumps(workspace, indent=2) + "\n")
            print(f"  wrote {filename}")
            return

        gen_dir = ctx.root / "projects" / ctx.project / _GEN_DIR
        gen_dir.mkdir(parents=True, exist_ok=True)
        canonical = gen_dir / filename

        # Single root folder — VS Code resolves relative paths from the
        # symlink location (workspace root), not the real file location.
        folders = [
            {"path": ".", "name": ctx.project},
        ]

        # Build files.exclude: hide repos and project dirs not in the active project.
        # Collapse owner/registry dirs when all their children are excluded.
        active_repos = set(ctx.repos.keys())
        excluded_repos = ctx.all_repos_on_disk - active_repos
        collapsed = _collapse_excludes(excluded_repos, ctx.all_repos_on_disk)
        excludes: dict[str, bool] = {".*": True}
        for path in sorted(collapsed):
            excludes[path] = True
        for project_path in sorted(ctx.all_project_paths):
            if project_path != ctx.project:
                excludes[f"projects/{project_path}"] = True

        # Merge: preserve existing keys (extensions, launch, tasks, etc.).
        # Replace folders and settings.files.exclude (managed keys).
        # Preserve all other settings keys.
        ws_data: dict[str, Any]
        if canonical.exists():
            ws_data = json.loads(canonical.read_text())
        else:
            ws_data = {}
        ws_data["folders"] = folders

        settings = ws_data.get("settings", {})
        if not isinstance(settings, dict):
            settings = {}
        settings["files.exclude"] = excludes
        ws_data["settings"] = settings

        canonical.write_text(json.dumps(ws_data, indent=2) + "\n")

        # Symlink at root — remove any existing file/symlink (possibly
        # with a different name from a previous project).
        self._cleanup_old_symlinks(ctx.root)
        link = ctx.root / filename
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(canonical.relative_to(ctx.root))

        n_excluded = len(excludes)
        print(f"  wrote projects/{ctx.project}/{_GEN_DIR}/{filename} ({n_excluded} excluded)")

    def deactivate(self, root: Path) -> None:
        self._cleanup_old_symlinks(root)

    def check(self, ctx: IntegrationContext) -> list[Issue]:
        issues: list[Issue] = []
        filename = _workspace_filename(ctx.project)

        if ctx.is_workspace_root:
            target = ctx.root / filename
            if not target.is_file():
                issues.append(
                    Issue(
                        integration=self.name,
                        message=f"{filename} missing in workspace dir",
                    )
                )
            return issues

        link = ctx.root / filename
        expected = Path("projects") / ctx.project / _GEN_DIR / filename
        if not link.is_symlink():
            issues.append(
                Issue(
                    integration=self.name,
                    message=f"{filename} symlink missing at workspace root",
                )
            )
        elif Path(os.readlink(link)) != expected:
            issues.append(
                Issue(
                    integration=self.name,
                    message=(f"{filename} symlink points to {os.readlink(link)}, expected {expected}"),
                )
            )
        return issues

    @staticmethod
    def _cleanup_old_symlinks(root: Path) -> None:
        """Remove any .code-workspace symlinks at root that point into .reporoot-derived/."""
        for entry in root.iterdir():
            if entry.is_symlink() and entry.name.endswith(_EXT) and _GEN_DIR in str(os.readlink(entry)):
                entry.unlink()
                print(f"  removed {entry.name} symlink")
