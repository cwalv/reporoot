"""reporoot — multi-repo workspace manager.

Manages workspaces of multiple git repos wired into ecosystem tools (npm, Go,
uv, etc.).  A project declares which repos belong together; workspaces are
checked-out instances of a project with git worktrees and integration files.

Commands:
  reporoot                          Show current context (root, project, workspace, repos)
  reporoot workspace <project>      Create/delete/sync/list workspaces
  reporoot fetch [source]           Fetch a project and clone its repos
  reporoot add <source>             Add a repo to the active project
  reporoot remove <path>            Remove a repo from the active project
  reporoot lock                     Snapshot repo versions for the active project
  reporoot lock-all                 Snapshot repo versions for all projects
  reporoot check                    Run convention enforcement checks
  reporoot prime                    Print project context for agent consumption
  reporoot setup claude             Register hooks in ~/.claude/settings.json
"""

from __future__ import annotations

import argparse
import sys


def _version() -> str:
    from importlib.metadata import version

    return version("reporoot")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="reporoot",
        description="Reporoot workspace manager",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    sub = parser.add_subparsers(dest="command")

    _raw = argparse.RawDescriptionHelpFormatter

    # reporoot workspace
    workspace_p = sub.add_parser(
        "workspace",
        help="Create, delete, sync, or list workspaces",
        description=(
            "Manage workspaces for a project. A workspace is a checked-out\n"
            "instance with git worktrees and integration files.\n"
            "\n"
            "  reporoot workspace myproject           Create default workspace\n"
            "  reporoot workspace myproject dev        Create named workspace\n"
            "  reporoot workspace myproject --delete   Delete default workspace\n"
            "  reporoot workspace myproject --sync     Sync with manifest\n"
            "  reporoot workspace myproject --list     List workspaces"
        ),
        formatter_class=_raw,
    )
    workspace_p.add_argument("project", help="Project name")
    workspace_p.add_argument("name", nargs="?", default="default", help="Workspace name (default: 'default')")
    workspace_p.add_argument("--delete", action="store_true", help="Delete the workspace")
    workspace_p.add_argument("--sync", action="store_true", help="Sync workspace with project manifest")
    workspace_p.add_argument("--list", action="store_true", dest="list_ws", help="List workspaces for the project")

    # reporoot add
    add_p = sub.add_parser(
        "add",
        help="Add a repo to the active project",
        description=(
            "Clone a repo into the workspace and register it in the active\n"
            "project's reporoot.yaml. Accepts a GitHub URL, a git remote URL,\n"
            "or a local path to a git repo."
        ),
        formatter_class=_raw,
    )
    add_p.add_argument("source", help="GitHub URL or local path to a git repo")
    add_p.add_argument("--project", "-p", help="Override: add to this project instead of the active one")
    add_p.add_argument("--role", "-r", help="Role annotation (primary, fork, dependency, reference)")
    add_p.add_argument("--note", "-n", help="Freeform note after the role annotation")
    add_p.add_argument("--as-project", dest="as_project", help="Add as a project repo to projects/{name}/")

    # reporoot remove
    remove_p = sub.add_parser(
        "remove",
        help="Remove a repo from the active project",
        description=(
            "Remove a repo entry from the active project's reporoot.yaml and\n"
            "re-run activation hooks. Optionally delete the clone from disk."
        ),
        formatter_class=_raw,
    )
    remove_p.add_argument("path", help="Local path of the repo (e.g., github/owner/repo)")
    remove_p.add_argument("--project", "-p", help="Override: remove from this project instead of the active one")
    remove_p.add_argument("--delete", action="store_true", help="Also delete the clone from disk")
    remove_p.add_argument("--force", action="store_true", help="With --delete, skip confirmation prompt")

    # reporoot fetch
    fetch_p = sub.add_parser(
        "fetch",
        help="Fetch a project and clone its repos",
        description=(
            "Clone a project repo and all the repos it references.\n"
            "Source can be a URL, registry/owner/project, or owner/project\n"
            "(defaults to github)."
        ),
        formatter_class=_raw,
    )
    fetch_p.add_argument("source", nargs="?", default=None, help="URL, registry/owner/project, or owner/project")

    # reporoot resolve
    sub.add_parser("resolve", help="Print the workspace root path")

    # reporoot lock
    sub.add_parser(
        "lock",
        help="Snapshot repo versions for the active project",
        description=(
            "Record each repo's current HEAD commit into the active project's\n"
            "reporoot.lock file. This captures the exact state of all repos,\n"
            "so another machine can reproduce it with 'reporoot fetch'."
        ),
        formatter_class=_raw,
    )

    # reporoot lock-all
    sub.add_parser(
        "lock-all",
        help="Snapshot repo versions for all projects",
        description=(
            "Update lock files for every project on disk, not just the active one.\n"
            "Useful when repos are shared across projects — commits made while\n"
            "working on one project also update the lock files of other projects\n"
            "that reference the same repos."
        ),
        formatter_class=_raw,
    )

    # reporoot check
    check_p = sub.add_parser(
        "check",
        help="Run convention enforcement checks",
        description=(
            "Scan all projects and repos for convention violations:\n"
            "- Orphaned clones (in a registry dir but not in any reporoot.yaml)\n"
            "- Dangling references (reporoot.yaml entry with no clone on disk)\n"
            "- Missing role annotations\n"
            "- Stale lock files\n"
            "- Integration-specific checks (missing tools, etc.)"
        ),
        formatter_class=_raw,
    )
    check_p.add_argument("-v", "--verbose", action="store_true", help="Show each issue individually instead of counts")

    # reporoot prime
    sub.add_parser(
        "prime",
        help="Print project context for agent consumption",
        description="Output reporoot project context (root, layout, doc locations) to stdout.\nDesigned to be called from a SessionStart or PreCompact hook.",
        formatter_class=_raw,
    )

    # reporoot setup
    setup_p = sub.add_parser(
        "setup",
        help="Configure agent integrations",
        description="Configure AI coding assistant integrations.",
        formatter_class=_raw,
    )
    setup_p.add_argument("integration", choices=["claude"], help="Integration to configure")

    args = parser.parse_args(argv)

    if args.command is None:
        _show_context()
        print()
        parser.print_help()
        sys.exit(1)

    if args.command == "workspace":
        from reporoot.activate import workspace_list, workspace_run

        if args.list_ws:
            workspace_list(args.project)
        else:
            workspace_run(args.project, args.name, delete=args.delete, sync=args.sync)
    elif args.command == "add":
        from reporoot.add import run

        run(
            source=args.source,
            project=args.project,
            role=args.role,
            note=args.note,
            as_project=args.as_project,
        )
    elif args.command == "remove":
        from reporoot.remove import run

        run(
            path=args.path,
            project=args.project,
            delete=args.delete,
            force=args.force,
        )
    elif args.command == "resolve":
        from reporoot.workspace import find_root

        print(find_root())
    elif args.command == "fetch":
        if args.source is None:
            from reporoot.workspace import infer_context, project_fetch_source

            ctx = infer_context()
            if ctx.project is None:
                raise SystemExit("fatal: cannot determine project (cd into a workspace or project directory)")
            source = project_fetch_source(ctx.root, ctx.project)
            if source:
                print(source)
            else:
                raise SystemExit(f"fatal: cannot determine fetch source for project '{ctx.project}'")
        else:
            from reporoot.fetch import run

            run(source=args.source)
    elif args.command == "lock":
        from reporoot.lock import run

        run()
    elif args.command == "lock-all":
        from reporoot.lock import run_all

        run_all()
    elif args.command == "check":
        from reporoot.check import run

        run(verbose=args.verbose)
    elif args.command == "prime":
        from reporoot.setup import prime

        prime()
    elif args.command == "setup":
        from reporoot.setup import setup_claude

        setup_claude()


def _show_context() -> None:
    """Display current context: root, project, workspace, and repos."""
    from reporoot.workspace import infer_context, list_workspaces, project_fetch_source, read_repos

    try:
        ctx = infer_context()
    except SystemExit:
        return

    print(f"       root: {ctx.root}")

    if ctx.project:
        print(f"    project: {ctx.project}")
        source = project_fetch_source(ctx.root, ctx.project)
        if source:
            print(f"      fetch: {source}")
        if ctx.workspace:
            print(f"  workspace: {ctx.workspace}")
        else:
            workspaces = list_workspaces(ctx.root, ctx.project)
            if workspaces:
                print(f" workspaces: {', '.join(workspaces)}")

        from reporoot.workspace import project_repos_file

        repos_file = project_repos_file(ctx.root, ctx.project)
        if repos_file.exists():
            repos = read_repos(repos_file)
            if repos:
                print("      repos:")
                for repo_path in repos:
                    print(f"        {repo_path}")
    else:
        print("no active project")
