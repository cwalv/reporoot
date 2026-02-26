"""gita integration — generate .gita/ config for multi-repo git operations."""

from __future__ import annotations

import shutil
from pathlib import Path

from reporoot.integrations.base import IntegrationContext, Issue

_DIR = ".gita"


class Gita:
    name = "gita"
    default_enabled = True

    def activate(self, ctx: IntegrationContext) -> None:
        gita_dir = ctx.root / _DIR
        gita_dir.mkdir(exist_ok=True)

        # repos.csv: path,name,flags (gita format)
        repos_lines = ["path,name,flags"]
        # groups by role
        groups: dict[str, list[str]] = {}

        for repo_path in sorted(ctx.repos):
            repo_dir = ctx.root / repo_path
            if not repo_dir.is_dir():
                continue
            # Use the repo basename as the gita name
            name = Path(repo_path).name
            repos_lines.append(f"{repo_dir},{name},")

            role = ctx.repos[repo_path].get("role", "")
            if role:
                groups.setdefault(role, []).append(name)

        (gita_dir / "repos.csv").write_text("\n".join(repos_lines) + "\n")

        # groups.csv: group,repos (space-separated)
        if groups:
            groups_lines = ["group,repos"]
            for group_name in sorted(groups):
                repos_str = " ".join(groups[group_name])
                groups_lines.append(f"{group_name},{repos_str}")
            (gita_dir / "groups.csv").write_text("\n".join(groups_lines) + "\n")

        print(f"  wrote {_DIR}/ ({len(repos_lines) - 1} repos, {len(groups)} groups)")

    def deactivate(self, root: Path) -> None:
        gita_dir = root / _DIR
        if gita_dir.is_dir():
            shutil.rmtree(gita_dir)
            print(f"  removed {_DIR}/")

    def check(self, ctx: IntegrationContext) -> list[Issue]:
        issues: list[Issue] = []
        if not shutil.which("gita"):
            issues.append(Issue(
                integration=self.name,
                message="gita not found on PATH (install with 'pip install gita')",
            ))
        return issues
