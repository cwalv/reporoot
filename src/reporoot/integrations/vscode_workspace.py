"""vscode-workspace integration — generate .code-workspace file."""

from __future__ import annotations

import json
from pathlib import Path

from reporoot.integrations.base import IntegrationContext, Issue

_FILE = "reporoot.code-workspace"


class VscodeWorkspace:
    name = "vscode-workspace"
    default_enabled = True

    def activate(self, ctx: IntegrationContext) -> None:
        folders = [{"path": "."}]  # root folder first
        for repo_path in sorted(ctx.repos):
            repo_dir = ctx.root / repo_path
            if repo_dir.is_dir():
                folders.append({"path": repo_path})

        workspace = {
            "folders": folders,
            "settings": {},
        }
        target = ctx.root / _FILE
        target.write_text(json.dumps(workspace, indent=2) + "\n")
        print(f"  wrote {_FILE} ({len(folders)} folders)")

    def deactivate(self, root: Path) -> None:
        target = root / _FILE
        if target.exists():
            target.unlink()
            print(f"  removed {_FILE}")

    def check(self, ctx: IntegrationContext) -> list[Issue]:
        return []
