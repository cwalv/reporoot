"""Tests for rr.git — low-level git helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from reporoot.git import (
    GitError,
    _urls_match,
    clone,
    clone_local,
    clone_or_update,
    current_branch,
    default_branch,
    export_repo,
    head_hash,
    remote_url,
    run_git,
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


class TestExportRepo:
    def test_export(self, git_repo: Path):
        data = export_repo(git_repo)
        assert data["url"] == "https://github.com/test-owner/test-repo.git"
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
