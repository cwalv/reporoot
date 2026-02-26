"""go-work integration — generate go.work for Go module repos."""

from __future__ import annotations

from pathlib import Path

from reporoot.integrations.base import IntegrationContext, Issue

_FILE = "go.work"


class GoWork:
    name = "go-work"
    default_enabled = True

    def activate(self, ctx: IntegrationContext) -> None:
        go_paths: list[str] = []
        for repo_path in sorted(ctx.repos):
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
        return []

    def _remove(self, path: Path) -> None:
        if path.exists():
            path.unlink()
            print(f"  removed {path.name}")
