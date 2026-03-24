"""reporoot setup — configure agent integrations."""

from __future__ import annotations

import json
from pathlib import Path


def prime() -> None:
    """Print reporoot project context to stdout for agent consumption.

    Outputs nothing (silently) if CWD is not inside a reporoot.
    Designed to be called from a SessionStart or PreCompact hook.
    """
    try:
        from reporoot.workspace import find_root, infer_context
        root = find_root()
    except SystemExit:
        return  # Not inside a reporoot — stay silent

    ctx = infer_context()

    lines = ["# Reporoot Project Context"]
    lines.append("")
    lines.append("reporoot is a multi-repo workspace manager. Run `reporoot --help` for commands.")

    try:
        from importlib.metadata import version as pkg_version
        ver = pkg_version("reporoot")
        # Only link to tagged releases (no .devN, +dirty, etc.)
        if ver and not any(c in ver for c in ("+", ".dev")):
            lines.append(f"Docs: https://github.com/cwalv/reporoot/blob/v{ver}/README.md")
    except Exception:
        pass

    lines.append("")
    lines.append(f"Root: {root}")

    if ctx.project:
        lines.append(f"Project: {ctx.project}")
    if ctx.workspace:
        lines.append(f"Workspace: {ctx.workspace}")
        lines.append(f"Workspace path: {root}/projects/{ctx.project}/workspaces/{ctx.workspace}/")

    lines.append("")
    lines.append("## Directory Structure")
    lines.append("")
    lines.append("  {registry}/  (github/, local/, etc.)")
    lines.append("      Bare repo stores — shared git objects; never work here directly")
    lines.append("  projects/{name}/")
    lines.append("      reporoot.yaml, reporoot.lock, project docs (.beads, docs/)")
    lines.append("  projects/{name}/workspaces/{ws}/")
    lines.append("      Isolated workspace: git worktrees mirroring registry layout,")
    lines.append("      generated ecosystem files (package.json, go.work, pyproject.toml),")
    lines.append("      isolated tool state (node_modules/, .venv/)")
    lines.append("")
    lines.append("  Working in a workspace: paths like github/owner/repo/ are worktrees,")
    lines.append("  not clones. The actual git store is at root/github/owner/repo.git/")

    print("\n".join(lines))


def setup_claude() -> None:
    """Register 'reporoot prime' in ~/.claude/settings.json hooks."""
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        raise SystemExit(f"fatal: {settings_path} not found — is Claude Code installed?")

    with open(settings_path) as f:
        settings = json.load(f)

    hook_entry = {"type": "command", "command": "reporoot prime"}
    changed = False

    for event in ("SessionStart", "PreCompact"):
        hooks_list = settings.setdefault("hooks", {}).setdefault(event, [])

        # Find or create the catch-all matcher block
        catch_all = next((h for h in hooks_list if h.get("matcher") == ""), None)
        if catch_all is None:
            catch_all = {"matcher": "", "hooks": []}
            hooks_list.append(catch_all)

        existing_cmds = [h.get("command") for h in catch_all.get("hooks", [])]
        if "reporoot prime" not in existing_cmds:
            catch_all.setdefault("hooks", []).append(hook_entry)
            changed = True

    if not changed:
        print("reporoot prime already registered in ~/.claude/settings.json")
        return

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    print(f"registered 'reporoot prime' in {settings_path} (SessionStart, PreCompact)")
