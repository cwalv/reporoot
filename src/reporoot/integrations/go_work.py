"""go-work integration — generate go.work for Go module repos."""

from __future__ import annotations

from pathlib import Path

from reporoot.integrations.base import IntegrationContext, Issue

_FILE = "go.work"


class GoWork:
    name = "go-work"
    default_enabled = True

    def activate(self, ctx: IntegrationContext) -> None:
        active = ctx.active_repos()
        go_paths: list[str] = []
        for repo_path in sorted(active):
            repo_dir = ctx.root / repo_path
            if repo_dir.is_dir() and (repo_dir / "go.mod").exists():
                go_paths.append(repo_path)

        target = ctx.root / _FILE
        if go_paths:
            uses = "\n".join(f"    ./{p}" for p in go_paths)
            go_work = f"go 1.21\n\nuse (\n{uses}\n)\n"
            target.write_text(go_work)
            print(f"  wrote {_FILE} ({len(go_paths)} modules)")
        else:
            self._remove(target)

    def deactivate(self, root: Path) -> None:
        self._remove(root / _FILE)

    def check(self, ctx: IntegrationContext) -> list[Issue]:
        issues: list[Issue] = []
        for repo_path in sorted(ctx.all_repos_on_disk - set(ctx.repos)):
            repo_dir = ctx.root / repo_path
            if repo_dir.is_dir() and (repo_dir / "go.mod").exists():
                issues.append(
                    Issue(
                        integration=self.name,
                        message=f"{repo_path} has go.mod but is not in the project manifest",
                        level="warning",
                    )
                )
        return issues

    def _remove(self, path: Path) -> None:
        if path.exists():
            path.unlink()
            print(f"  removed {path.name}")
