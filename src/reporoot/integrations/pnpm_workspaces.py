"""pnpm-workspaces integration — generate pnpm-workspace.yaml and run pnpm install."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from reporoot.integrations.base import IntegrationContext, Issue
from reporoot.integrations.run import run_tool

_FILE = "pnpm-workspace.yaml"


class PnpmWorkspaces:
    name = "pnpm-workspaces"
    default_enabled = False

    def activate(self, ctx: IntegrationContext) -> None:
        active = ctx.active_repos()
        node_paths: list[str] = []
        for repo_path in sorted(active):
            repo_dir = ctx.root / repo_path
            if repo_dir.is_dir() and (repo_dir / "package.json").exists():
                node_paths.append(repo_path)

        target = ctx.root / _FILE
        if node_paths:
            data = {"packages": node_paths}
            with open(target, "w") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            print(f"  wrote {_FILE} ({len(node_paths)} packages)")
            pnpm = shutil.which("pnpm")
            if pnpm:
                run_tool([pnpm, "install"], cwd=ctx.root)
        else:
            self._remove(target)

    def deactivate(self, root: Path) -> None:
        self._remove(root / _FILE)

    def check(self, ctx: IntegrationContext) -> list[Issue]:
        issues: list[Issue] = []
        node_paths = [p for p in ctx.repos if (ctx.root / p).is_dir() and (ctx.root / p / "package.json").exists()]
        if node_paths and not shutil.which("pnpm"):
            issues.append(
                Issue(
                    integration=self.name,
                    message="pnpm not found on PATH (needed for pnpm workspaces)",
                )
            )
        return issues

    def _remove(self, path: Path) -> None:
        if path.exists():
            path.unlink()
            print(f"  removed {path.name}")
