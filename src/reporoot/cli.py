"""reporoot — workspace manager.

Conventions:
- Normal repos at {registry}/{owner}/{repo}/ (code, build tools see these)
- Project repos at projects/{name}/ (coordination, build tools ignore these)
- One project active at a time (.reporoot-active), drives ecosystem workspace files
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
        description="Reporoot manager",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    sub = parser.add_subparsers(dest="command")

    _raw = argparse.RawDescriptionHelpFormatter

    # reporoot activate
    activate_p = sub.add_parser(
        "activate",
        help="Set the active project and run integrations",
        description=(
            "Set the active project, write .reporoot-active, and run all\n"
            "enabled integrations (npm workspaces, go work, uv, gita, vscode).\n"
            "Switching projects automatically cleans up the previous project's\n"
            "derived files before generating new ones."
        ),
        formatter_class=_raw,
    )
    activate_p.add_argument("project", help="Project name")

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

    # reporoot deactivate
    deactivate_p = sub.add_parser(
        "deactivate",
        help="Remove derived files, clear active project",
        description=(
            "Remove all integration-generated files (package.json, go.work,\n"
            "pyproject.toml, .gita/, .code-workspace) and clear the active\n"
            "project pointer.\n"
            "\n"
            "With --hard, also removes everything at root that isn't a known\n"
            "registry directory or projects/ — tool state like node_modules,\n"
            ".venv, lock files, build output, etc. Each item is confirmed\n"
            "interactively unless --force is passed."
        ),
        formatter_class=_raw,
    )
    deactivate_p.add_argument(
        "--hard",
        action="store_true",
        help="Also remove all non-repo content at root (node_modules, .venv, lock files, etc.)",
    )
    deactivate_p.add_argument(
        "--force",
        action="store_true",
        help="With --hard, skip confirmation prompts",
    )

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

    args = parser.parse_args(argv)

    if args.command is None:
        from reporoot.workspace import active_project, find_root, project_fetch_source

        try:
            root = find_root()
            project = active_project(root)
            if project:
                print(f"active project: {project}")
                source = project_fetch_source(root, project)
                if source:
                    print(f"         fetch: {source}")
            else:
                print("no active project")
        except SystemExit:
            pass
        print()
        parser.print_help()
        sys.exit(1)

    if args.command == "activate":
        from reporoot.activate import run

        run(project=args.project)
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
    elif args.command == "deactivate":
        from reporoot.activate import deactivate

        deactivate(hard=args.hard, force=args.force)
    elif args.command == "resolve":
        from reporoot.workspace import find_root

        print(find_root())
    elif args.command == "fetch":
        if args.source is None:
            from reporoot.workspace import find_root, project_fetch_source, require_active_project

            root = find_root()
            project = require_active_project(root)
            source = project_fetch_source(root, project)
            if source:
                print(source)
            else:
                raise SystemExit(f"fatal: cannot determine fetch source for project '{project}'")
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
