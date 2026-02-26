"""reporoot — workspace manager.

Conventions:
- Normal repos at {registry}/{owner}/{repo}/ (code, build tools see these)
- Project repos at projects/{name}/ (coordination, build tools ignore these)
- One project active at a time (.rr-active), drives ecosystem workspace files
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="reporoot",
        description="Reporoot manager",
    )
    sub = parser.add_subparsers(dest="command")

    # reporoot activate
    activate_p = sub.add_parser("activate", help="Set the active project")
    activate_p.add_argument("project", help="Project name (or 'none' to deactivate)")

    # reporoot add
    add_p = sub.add_parser("add", help="Add a repo to the active project")
    add_p.add_argument("source", help="GitHub URL or local path to a git repo")
    add_p.add_argument("--project", "-p", help="Override: add to this project instead of the active one")
    add_p.add_argument("--role", "-r", help="Role annotation (primary, fork, dependency, reference)")
    add_p.add_argument("--note", "-n", help="Freeform note after the role annotation")
    add_p.add_argument("--as-project", dest="as_project", help="Add as a project repo to projects/{name}/")

    # reporoot fetch
    fetch_p = sub.add_parser("fetch", help="Fetch a project and import its repos")
    fetch_p.add_argument("source", help="URL, registry/owner/project, or owner/project")

    # reporoot reset
    reset_p = sub.add_parser("reset", help="Deactivate: remove derived files, clear pointer")
    reset_p.add_argument(
        "--hard", action="store_true",
        help="Also remove all non-repo content at root (node_modules, .venv, lock files, etc.)",
    )
    reset_p.add_argument(
        "--force", action="store_true",
        help="With --hard, skip confirmation prompts",
    )

    # reporoot lock
    sub.add_parser("lock", help="Regenerate lock file for the active project")

    # reporoot lock-all
    sub.add_parser("lock-all", help="Regenerate lock files for all projects")

    # reporoot check
    sub.add_parser("check", help="Convention enforcement checks (scans all projects)")

    args = parser.parse_args(argv)

    if args.command is None:
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
    elif args.command == "reset":
        from reporoot.activate import reset
        reset(hard=args.hard, force=args.force)
    elif args.command == "fetch":
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
        run()
