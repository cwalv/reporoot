"""Tests for rr.git — low-level git helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from reporoot.git import (
    GitError,
    _urls_match,
    clone,
    clone_bare,
    clone_local,
    clone_or_update,
    current_branch,
    default_branch,
    export_repo,
    head_hash,
    is_bare_repo,
    remote_url,
    run_git,
    worktree_add,
    worktree_list,
    worktree_remove,
)


class TestRunGit:
    def test_success(self, git_repo: Path):
        result = run_git("-C", str(git_repo), "status")
        assert result.returncode == 0

    def test_failure_raises(self, tmp_path: Path):
        with pytest.raises(GitError) as exc_info:
            run_git("-C", str(tmp_path), "log")
        assert exc_info.value.returncode != 0

    def test_check_false(self, tmp_path: Path):
        result = run_git("-C", str(tmp_path), "log", check=False)
        assert result.returncode != 0


class TestQueryCommands:
    def test_remote_url(self, git_repo: Path):
        assert remote_url(git_repo) == "https://github.com/test-owner/test-repo.git"

    def test_head_hash(self, git_repo: Path):
        h = head_hash(git_repo)
        assert len(h) == 40
        assert all(c in "0123456789abcdef" for c in h)

    def test_current_branch(self, git_repo: Path):
        branch = current_branch(git_repo)
        assert branch in ("main", "master")

    def test_default_branch(self, git_repo: Path):
        branch = default_branch(git_repo)
        assert branch in ("main", "master")

    def test_remote_url_bare(self, bare_repo: Path):
        url = remote_url(bare_repo)
        # Bare clone of a local repo — URL is the local path
        assert "repo" in url

    def test_head_hash_bare(self, bare_repo: Path):
        h = head_hash(bare_repo)
        assert len(h) == 40

    def test_remote_url_worktree(self, bare_repo: Path, tmp_path: Path):
        wt = tmp_path / "wt"
        worktree_add(bare_repo, wt, "wt-branch")
        url = remote_url(wt)
        assert "repo" in url

    def test_head_hash_worktree(self, bare_repo: Path, tmp_path: Path):
        wt = tmp_path / "wt"
        worktree_add(bare_repo, wt, "wt-branch")
        h = head_hash(wt)
        assert len(h) == 40


class TestIsBareRepo:
    def test_bare_repo(self, bare_repo: Path):
        assert is_bare_repo(bare_repo)

    def test_regular_repo(self, git_repo: Path):
        assert not is_bare_repo(git_repo)

    def test_not_a_repo(self, tmp_path: Path):
        assert not is_bare_repo(tmp_path)

    def test_worktree(self, bare_repo: Path, tmp_path: Path):
        wt = tmp_path / "wt"
        worktree_add(bare_repo, wt, "wt-branch")
        assert not is_bare_repo(wt)


class TestExportRepo:
    def test_export(self, git_repo: Path):
        data = export_repo(git_repo)
        assert data["url"] == "https://github.com/test-owner/test-repo.git"
        assert len(data["version"]) == 40

    def test_export_bare(self, bare_repo: Path):
        data = export_repo(bare_repo)
        assert len(data["version"]) == 40


class TestClone:
    def test_clone_local(self, git_repo: Path, tmp_path: Path):
        target = tmp_path / "cloned"
        clone_local(git_repo, target, "https://github.com/test-owner/test-repo.git")
        assert (target / "README.md").exists()
        assert remote_url(target) == "https://github.com/test-owner/test-repo.git"

    def test_clone_or_update_new(self, git_repo: Path, tmp_path: Path):
        target = tmp_path / "new-clone"
        status = clone_or_update(str(git_repo), target)
        assert status == "cloned"
        assert (target / "README.md").exists()

    def test_clone_or_update_existing_skip(self, git_repo: Path, tmp_path: Path):
        target = tmp_path / "existing"
        clone(str(git_repo), target)
        status = clone_or_update(str(git_repo), target, skip_existing=True)
        assert status == "updated"

    def test_clone_or_update_exists_no_skip(self, git_repo: Path, tmp_path: Path):
        target = tmp_path / "existing"
        target.mkdir()
        status = clone_or_update(str(git_repo), target)
        assert status == "exists"


class TestCloneBare:
    def test_clone_bare(self, git_repo: Path, tmp_path: Path):
        target = tmp_path / "test.git"
        clone_bare(str(git_repo), target)
        assert target.exists()
        assert is_bare_repo(target)
        # Bare repos have no working tree files
        assert not (target / "README.md").exists()
        # But have git objects
        assert (target / "HEAD").exists()

    def test_clone_or_update_bare_new(self, git_repo: Path, tmp_path: Path):
        target = tmp_path / "test.git"
        status = clone_or_update(str(git_repo), target, bare=True)
        assert status == "cloned"
        assert is_bare_repo(target)

    def test_clone_or_update_bare_existing_skip(self, git_repo: Path, tmp_path: Path):
        target = tmp_path / "test.git"
        clone_bare(str(git_repo), target)
        status = clone_or_update(str(git_repo), target, bare=True, skip_existing=True)
        assert status == "updated"


class TestWorktreeAdd:
    def test_basic(self, bare_repo: Path, tmp_path: Path):
        wt = tmp_path / "worktree"
        worktree_add(bare_repo, wt, "feature-branch")
        assert wt.exists()
        assert (wt / "README.md").exists()
        # .git is a file in worktrees, not a directory
        assert (wt / ".git").is_file()
        assert current_branch(wt) == "feature-branch"

    def test_with_track(self, bare_repo: Path, tmp_path: Path):
        wt = tmp_path / "worktree"
        # The bare repo has origin/master or origin/main — find which
        branch = current_branch(bare_repo)
        worktree_add(bare_repo, wt, "ws/main", track=f"origin/{branch}")
        assert (wt / "README.md").exists()
        assert current_branch(wt) == "ws/main"

    def test_with_start_point(self, bare_repo: Path, tmp_path: Path):
        wt = tmp_path / "worktree"
        worktree_add(bare_repo, wt, "new-branch", start_point="HEAD")
        assert (wt / "README.md").exists()
        assert current_branch(wt) == "new-branch"


class TestWorktreeRemove:
    def test_remove(self, bare_repo: Path, tmp_path: Path):
        wt = tmp_path / "worktree"
        worktree_add(bare_repo, wt, "to-remove")
        assert wt.exists()
        worktree_remove(bare_repo, wt)
        assert not wt.exists()

    def test_remove_force(self, bare_repo: Path, tmp_path: Path):
        wt = tmp_path / "worktree"
        worktree_add(bare_repo, wt, "to-force-remove")
        # Create an untracked file to make it "dirty"
        (wt / "untracked.txt").write_text("dirty")
        worktree_remove(bare_repo, wt, force=True)
        assert not wt.exists()


class TestWorktreeList:
    def test_empty(self, bare_repo: Path):
        worktrees = worktree_list(bare_repo)
        assert worktrees == []

    def test_one_worktree(self, bare_repo: Path, tmp_path: Path):
        wt = tmp_path / "worktree"
        worktree_add(bare_repo, wt, "listed-branch")
        worktrees = worktree_list(bare_repo)
        assert len(worktrees) == 1
        assert worktrees[0].path == wt.resolve()
        assert worktrees[0].branch == "listed-branch"
        assert len(worktrees[0].head) == 40

    def test_multiple_worktrees(self, bare_repo: Path, tmp_path: Path):
        wt1 = tmp_path / "wt1"
        wt2 = tmp_path / "wt2"
        worktree_add(bare_repo, wt1, "branch-1")
        worktree_add(bare_repo, wt2, "branch-2")
        worktrees = worktree_list(bare_repo)
        assert len(worktrees) == 2
        branches = {w.branch for w in worktrees}
        assert branches == {"branch-1", "branch-2"}


class TestUrlsMatch:
    def test_same(self):
        assert _urls_match(
            "https://github.com/owner/repo.git",
            "https://github.com/owner/repo.git",
        )

    def test_with_without_git_suffix(self):
        assert _urls_match(
            "https://github.com/owner/repo.git",
            "https://github.com/owner/repo",
        )

    def test_ssh_vs_https(self):
        assert _urls_match(
            "git@github.com:owner/repo.git",
            "https://github.com/owner/repo.git",
        )

    def test_different_repos(self):
        assert not _urls_match(
            "https://github.com/owner/repo-a.git",
            "https://github.com/owner/repo-b.git",
        )

    def test_trailing_slash(self):
        assert _urls_match(
            "https://github.com/owner/repo/",
            "https://github.com/owner/repo.git",
        )
