"""vscode-workspace integration — generate .code-workspace file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reporoot.integrations.base import IntegrationContext, Issue

_EXT = ".code-workspace"


def _workspace_filename(project: str) -> str:
    """Derive workspace filename from project name (uses leaf segment)."""
    return Path(project).name + _EXT


class VscodeWorkspace:
    name = "vscode-workspace"
    default_enabled = True

    def activate(self, ctx: IntegrationContext) -> None:
        filename = _workspace_filename(ctx.project)
        target = ctx.root / filename

        folder_name = ctx.workspace_name or ctx.project
        folders: list[dict[str, str]] = [
            {"path": ".", "name": f"workspace ({folder_name})"},
        ]

        workspace: dict[str, Any]
        if target.is_symlink():
            target.unlink()
            workspace = {}
        elif target.exists():
            workspace = json.loads(target.read_text())
        else:
            workspace = {}

        workspace["folders"] = folders

        settings = workspace.setdefault("settings", {})
        if not isinstance(settings, dict):
            settings = {}
        # Prevent VS Code from walking up to the parent repo and greying out
        # the workspace dir (which is gitignored as a worktree).
        settings["git.autoRepositoryDetection"] = "subFolders"
        # Needed to discover repos at registry/owner/repo depth.
        settings["git.repositoryScanMaxDepth"] = 3
        workspace["settings"] = settings

        target.write_text(json.dumps(workspace, indent=2) + "\n")
        print(f"  wrote {filename}")

    def deactivate(self, root: Path) -> None:
        for entry in root.iterdir():
            if not entry.name.endswith(_EXT):
                continue
            if entry.is_symlink():
                entry.unlink()
                print(f"  removed {entry.name} symlink")
            elif entry.is_file():
                entry.unlink()
                print(f"  removed {entry.name}")

    def check(self, ctx: IntegrationContext) -> list[Issue]:
        filename = _workspace_filename(ctx.project)
        target = ctx.root / filename
        if not target.is_file() or target.is_symlink():
            return [
                Issue(
                    integration=self.name,
                    message=f"{filename} missing",
                )
            ]
        return []
