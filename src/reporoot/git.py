"""Low-level git helpers — thin wrappers around subprocess."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


def run_git(
    *args: str,
    cwd: str | Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the CompletedProcess."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        cmd = " ".join(["git", *args])
        raise GitError(cmd, result.returncode, result.stderr.strip())
    return result


class GitError(Exception):
    def __init__(self, cmd: str, returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"git command failed ({returncode}): {cmd}\n{stderr}")


# --- Query commands ---


def remote_url(repo: Path) -> str:
    """Get origin remote URL. Works for regular repos, bare repos, and worktrees."""
    return run_git("-C", str(repo), "remote", "get-url", "origin").stdout.strip()


def head_hash(repo: Path) -> str:
    """Get HEAD commit hash. Works for regular repos, bare repos, and worktrees."""
    return run_git("-C", str(repo), "rev-parse", "HEAD").stdout.strip()


def current_branch(repo: Path) -> str:
    """Get current branch name, or 'HEAD' if detached."""
    return run_git("-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def default_branch(repo: Path) -> str:
    """Get current branch, falling back to 'main' if detached."""
    branch = current_branch(repo)
    return branch if branch != "HEAD" else "main"


def is_bare_repo(path: Path) -> bool:
    """Check if path is a bare git repository."""
    result = run_git("-C", str(path), "rev-parse", "--is-bare-repository", check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


# --- Export ---


def export_repo(repo: Path) -> dict[str, str]:
    """Export a repo's state: url + exact version (commit hash).

    Works for regular repos, bare repos, and worktrees.
    """
    return {
        "url": remote_url(repo),
        "version": head_hash(repo),
    }


# --- Clone / checkout ---


def clone(url: str, target: Path, *, shallow: bool = False) -> None:
    """Clone a repo from a URL."""
    cmd = ["clone"]
    if shallow:
        cmd += ["--depth", "1"]
    cmd += [url, str(target)]
    run_git(*cmd)


def clone_bare(url: str, target: Path) -> None:
    """Clone a repo as a bare repository.

    Reconfigures the fetch refspec so remote-tracking branches land under
    refs/remotes/origin/* (bare clone default puts them in refs/heads/*).
    This is required for worktree --track to resolve origin/<branch>.
    """
    run_git("clone", "--bare", url, str(target))
    run_git(
        "-C",
        str(target),
        "config",
        "remote.origin.fetch",
        "+refs/heads/*:refs/remotes/origin/*",
    )
    run_git("-C", str(target), "fetch", "origin")


def clone_local(source: Path, target: Path, remote_url: str) -> None:
    """Clone from a local repo, then restore the real remote URL."""
    run_git("clone", "--local", str(source), str(target))
    run_git("-C", str(target), "remote", "set-url", "origin", remote_url)


def fetch(repo: Path, remote: str = "origin") -> None:
    """Fetch from remote. Works for regular repos, bare repos, and worktrees."""
    run_git("-C", str(repo), "fetch", remote)


def checkout(repo: Path, ref: str) -> None:
    """Checkout a ref (branch, tag, or commit hash)."""
    run_git("-C", str(repo), "checkout", ref)


def clone_or_update(
    url: str,
    target: Path,
    version: str | None = None,
    *,
    shallow: bool = False,
    skip_existing: bool = False,
    bare: bool = False,
) -> str:
    """Clone a repo, or fetch+checkout if it already exists.

    Returns a short status string: 'cloned', 'updated', 'skipped', 'exists'.
    When bare=True, clones as a bare repo and ignores version/shallow.
    """
    if target.exists():
        if skip_existing:
            try:
                existing_url = remote_url(target)
            except GitError:
                return "skipped (not a git repo)"
            if _urls_match(existing_url, url):
                fetch(target)
                if version and not bare:
                    checkout(target, version)
                return "updated"
            return "skipped (different repo)"
        return "exists"

    if bare:
        clone_bare(url, target)
    else:
        clone(url, target, shallow=shallow)
        if version:
            checkout(target, version)
    return "cloned"


# --- Worktrees ---


@dataclass
class WorktreeInfo:
    """Parsed output from git worktree list --porcelain."""

    path: Path
    head: str
    branch: str | None  # None if detached


def worktree_add(
    bare_repo: Path,
    dest: Path,
    branch: str,
    *,
    track: str | None = None,
    start_point: str | None = None,
) -> None:
    """Create a git worktree from a bare (or regular) repo.

    Args:
        bare_repo: Path to the bare repo (or any repo).
        dest: Where to place the worktree.
        branch: Branch name to create (via -b).
        track: If set, pass --track and use this as the start point
               (e.g. 'origin/main').
        start_point: Starting ref for the new branch. If track is set,
                     this defaults to track.
    """
    cmd = ["-C", str(bare_repo), "worktree", "add", str(dest), "-b", branch]
    if track:
        cmd.append("--track")
        if not start_point:
            start_point = track
    if start_point:
        cmd.append(start_point)
    run_git(*cmd)


def worktree_remove(bare_repo: Path, dest: Path, *, force: bool = False) -> None:
    """Remove a git worktree."""
    cmd = ["-C", str(bare_repo), "worktree", "remove", str(dest)]
    if force:
        cmd.append("--force")
    run_git(*cmd)


def worktree_list(bare_repo: Path) -> list[WorktreeInfo]:
    """List worktrees for a repo (bare or regular).

    Returns parsed WorktreeInfo for each worktree, excluding the bare repo
    itself (which appears as a worktree entry with "(bare)").
    """
    result = run_git("-C", str(bare_repo), "worktree", "list", "--porcelain")
    worktrees: list[WorktreeInfo] = []
    path: Path | None = None
    head = ""
    branch: str | None = None
    is_bare = False

    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            path = Path(line.split(" ", 1)[1])
        elif line.startswith("HEAD "):
            head = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            branch = line.split(" ", 1)[1]
            # Strip refs/heads/ prefix
            if branch.startswith("refs/heads/"):
                branch = branch[len("refs/heads/") :]
        elif line == "detached":
            branch = None
        elif line == "bare":
            is_bare = True
        elif line == "":
            if path is not None and not is_bare:
                worktrees.append(WorktreeInfo(path=path, head=head, branch=branch))
            path = None
            head = ""
            branch = None
            is_bare = False

    # Handle last entry (no trailing blank line)
    if path is not None and not is_bare:
        worktrees.append(WorktreeInfo(path=path, head=head, branch=branch))

    return worktrees


# --- URL matching ---


def _urls_match(a: str, b: str) -> bool:
    """Loose URL comparison (ignore trailing .git and protocol differences)."""

    def normalize(u: str) -> str:
        u = u.rstrip("/").removesuffix(".git")
        # git@github.com:owner/repo -> github.com/owner/repo
        if u.startswith("git@"):
            u = u[4:].replace(":", "/", 1)
        if "://" in u:
            u = u.split("://", 1)[1]
        return u.lower()

    return normalize(a) == normalize(b)
