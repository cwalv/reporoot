"""project-script integration — run project-provided scripts on activate/check.

When enabled, looks for executable scripts in the project directory:
  projects/{name}/activate  — run during workspace activation
  projects/{name}/check     — run during reporoot check

Scripts receive the workspace root as the first argument.
Default disabled — must be explicitly enabled in reporoot.yaml:

  integrations:
    project-script:
      enabled: true
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from reporoot.integrations.base import IntegrationContext, Issue


class ProjectScript:
    name = "project-script"
    default_enabled = False

    def activate(self, ctx: IntegrationContext) -> None:
        script = self._find_script(ctx, "activate")
        if script:
            self._run(script, ctx.root)

    def deactivate(self, root: Path) -> None:
        pass  # No generated files to clean up

    def check(self, ctx: IntegrationContext) -> list[Issue]:
        script = self._find_script(ctx, "check")
        if not script:
            return []
        result = subprocess.run(
            [str(script), str(ctx.root)],
            capture_output=True,
            text=True,
        )
        issues: list[Issue] = []
        if result.returncode != 0:
            msg = result.stdout.strip() or result.stderr.strip() or f"check script exited {result.returncode}"
            issues.append(Issue(integration=self.name, message=msg))
        return issues

    def _find_script(self, ctx: IntegrationContext, name: str) -> Path | None:
        """Find a project-level script by name."""
        if ctx.is_workspace_root:
            # ctx.root = .../projects/{project}/workspaces/{ws}/
            project_dir = ctx.root.parent.parent
        else:
            # ctx.root is the reporoot itself
            project_dir = ctx.root / "projects" / ctx.project

        script = project_dir / name
        if script.is_file():
            return script
        return None

    def _run(self, script: Path, root: Path) -> None:
        print(f"  running {script.name}")
        result = subprocess.run(
            [str(script), str(root)],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(f"    {line}")
        if result.returncode != 0:
            print(f"  warning: {script.name} exited {result.returncode}")
            if result.stderr.strip():
                for line in result.stderr.strip().splitlines():
                    print(f"    {line}")
