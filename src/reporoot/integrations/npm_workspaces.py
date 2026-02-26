"""npm-workspaces integration — generate root package.json with workspaces array."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from reporoot.integrations.base import IntegrationContext, Issue
from reporoot.integrations.run import run_tool

_FILE = "package.json"


class NpmWorkspaces:
    name = "npm-workspaces"
    default_enabled = True

    def activate(self, ctx: IntegrationContext) -> None:
        node_paths: list[str] = []
        for repo_path in sorted(ctx.repos):
            repo_dir = ctx.root / repo_path
            if repo_dir.is_dir() and (repo_dir / "package.json").exists():
                node_paths.append(repo_path)

        target = ctx.root / _FILE
        if node_paths:
            pkg = {
                "name": "reporoot",
                "private": True,
                "workspaces": node_paths,
            }
            target.write_text(json.dumps(pkg, indent=2) + "\n")
            print(f"  wrote {_FILE} ({len(node_paths)} workspaces)")
            npm = shutil.which("npm")
            if npm:
                run_tool([npm, "install"], cwd=ctx.root)
        else:
            self._remove(target)

    def deactivate(self, root: Path) -> None:
        self._remove(root / _FILE)

    def check(self, ctx: IntegrationContext) -> list[Issue]:
        issues: list[Issue] = []
        # Check if npm is available
        node_paths = [
            p for p in ctx.repos
            if (ctx.root / p).is_dir() and (ctx.root / p / "package.json").exists()
        ]
        if node_paths and not shutil.which("npm"):
            issues.append(Issue(
                integration=self.name,
                message="npm not found on PATH (needed for npm workspaces)",
            ))
        return issues

    def _remove(self, path: Path) -> None:
        if path.exists():
            path.unlink()
            print(f"  removed {path.name}")
