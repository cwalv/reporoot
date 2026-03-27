"""reporoot add — add a repo to a project.

Usage:
  reporoot add <url>                              Clone from URL to {registry}/{owner}/{repo}/
  reporoot add <local-path>                       Move local repo (reads its remote)
  reporoot add <source> --role r                  Set role
  reporoot add <source> --project p               Add to a specific project
  reporoot add <source> --workspace w             Target a specific workspace
  reporoot add <source> --as-project name         Add as a project repo to projects/{name}/
"""

from __future__ import annotations

from pathlib import Path

from reporoot.config import normalize_repo_url, parse_repo_url
from reporoot.git import (
    GitError,
    clone,
    clone_bare,
    clone_local,
    default_branch,
    remote_url,
    worktree_add,
)
from reporoot.integrations.registry import run_activate
from reporoot.workspace import (
    append_entry,
    bare_repo_path,
    find_root,
    project_repos_file,
    read_repos,
    read_repos_full,
    require_context,
    workspace_dir,
)


def _is_url(source: str) -> bool:
    return source.startswith(("https://", "http://", "git@"))


def _is_local_repo(source: str) -> bool:
    p = Path(source).expanduser().resolve()
    return p.is_dir() and (p / ".git").exists()


def run(
    source: str,
    project: str | None = None,
    workspace: str | None = None,
    role: str | None = None,
    note: str | None = None,
    as_project: str | None = None,
) -> None:
    # Resolve source to a URL + registry/owner/repo
    if _is_url(source):
        url = source
        registry, owner, repo = parse_repo_url(url)
        source_path = None
    elif _is_local_repo(source):
        source_path = Path(source).expanduser().resolve()
        url = remote_url(source_path)
        registry, owner, repo = parse_repo_url(url)
    else:
        raise SystemExit(f"fatal: {source} is not a URL or a local git repo")

    canonical_url = normalize_repo_url(registry, owner, repo)

    # --as-project: clone directly, no workspace involvement
    if as_project:
        root = find_root()
        local_path = f"projects/{as_project}"
        target = root / local_path
        print(f"add: {local_path}")
        if target.exists():
            print("  already on disk, skipping clone")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                if source_path:
                    print(f"  git clone --local {source_path} -> {target}")
                    clone_local(source_path, target, canonical_url)
                else:
                    print(f"  git clone {url} -> {target}")
                    clone(url, target)
            except GitError as e:
                raise SystemExit(f"fatal: {e}")
        return

    # Normal flow: bare clone + worktree
    ctx = require_context(project=project, workspace=workspace)
    root = ctx.root
    local_path = f"{registry}/{owner}/{repo}"

    bare_path = bare_repo_path(root, local_path)
    print(f"add: {local_path}")

    if bare_path.exists():
        print("  bare repo already exists, skipping clone")
    else:
        bare_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if source_path:
                print(f"  git clone --bare {source_path} -> {bare_path}")
                clone_bare(str(source_path), bare_path)
            else:
                print(f"  git clone --bare {url} -> {bare_path}")
                clone_bare(url, bare_path)
        except GitError as e:
            raise SystemExit(f"fatal: {e}")

    # Add worktree to workspace
    ws_dir = workspace_dir(root, ctx.project, ctx.workspace)
    wt_dest = ws_dir / local_path
    if wt_dest.exists():
        print(f"  worktree already exists: {local_path}")
    else:
        wt_dest.parent.mkdir(parents=True, exist_ok=True)
        version = default_branch(bare_path)
        branch = f"{ctx.workspace}/{version}"
        track = f"origin/{version}"
        worktree_add(bare_path, wt_dest, branch, track=track)
        print(f"  worktree: {local_path} ({branch} -> {track})")

    version = default_branch(bare_path)

    # Add to project reporoot.yaml
    repos_file = project_repos_file(root, ctx.project)
    if not repos_file.parent.exists():
        print(f"  warning: project dir projects/{ctx.project}/ does not exist, skipping reporoot.yaml update")
    else:
        append_entry(repos_file, local_path, canonical_url, version, role=role, note=note)
        # Regenerate integration files
        repos = read_repos(repos_file)
        full = read_repos_full(repos_file)
        integrations_config = full.get("integrations", {})
        activate_root = workspace_dir(root, ctx.project, ctx.workspace)
        run_activate(activate_root, ctx.project, repos, integrations_config)
