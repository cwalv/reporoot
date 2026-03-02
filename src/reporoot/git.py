"""Low-level git helpers — thin wrappers around subprocess."""

from __future__ import annotations

import subprocess
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
    """Get origin remote URL."""
    return run_git("-C", str(repo), "remote", "get-url", "origin").stdout.strip()


def head_hash(repo: Path) -> str:
    """Get HEAD commit hash."""
    return run_git("-C", str(repo), "rev-parse", "HEAD").stdout.strip()


def current_branch(repo: Path) -> str:
    """Get current branch name, or 'HEAD' if detached."""
    return run_git("-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def default_branch(repo: Path) -> str:
    """Get current branch, falling back to 'main' if detached."""
    branch = current_branch(repo)
    return branch if branch != "HEAD" else "main"


# --- Export ---


def export_repo(repo: Path) -> dict[str, str]:
    """Export a repo's state: url + exact version (commit hash)."""
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


def clone_local(source: Path, target: Path, remote_url: str) -> None:
    """Clone from a local repo, then restore the real remote URL."""
    run_git("clone", "--local", str(source), str(target))
    run_git("-C", str(target), "remote", "set-url", "origin", remote_url)


def fetch(repo: Path, remote: str = "origin") -> None:
    """Fetch from remote."""
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
) -> str:
    """Clone a repo, or fetch+checkout if it already exists.

    Returns a short status string: 'cloned', 'updated', 'skipped', 'exists'.
    """
    if target.exists():
        if skip_existing:
            # Check if it's the same repo
            try:
                existing_url = remote_url(target)
            except GitError:
                return "skipped (not a git repo)"
            # Normalize for comparison
            if _urls_match(existing_url, url):
                fetch(target)
                if version:
                    checkout(target, version)
                return "updated"
            return "skipped (different repo)"
        return "exists"

    clone(url, target, shallow=shallow)
    if version:
        checkout(target, version)
    return "cloned"


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
