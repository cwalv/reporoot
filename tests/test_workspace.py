"""Tests for rr.workspace — root finding, URL parsing, .repos I/O, active project."""

from __future__ import annotations

from pathlib import Path

import pytest

from reporoot.workspace import (
    active_project,
    all_known_repos,
    all_project_repos_files,
    append_entry,
    find_root,
    normalize_github_url,
    parse_github_url,
    project_lock_file,
    project_repos_file,
    read_repos,
    require_active_project,
)


class TestFindRoot:
    def test_finds_by_github_dir(self, tmp_path: Path):
        (tmp_path / "github").mkdir()
        assert find_root(tmp_path) == tmp_path

    def test_finds_by_projects_dir(self, tmp_path: Path):
        (tmp_path / "projects").mkdir()
        assert find_root(tmp_path) == tmp_path

    def test_finds_by_rr_active(self, tmp_path: Path):
        (tmp_path / ".reporoot-active").write_text("myproject\n")
        assert find_root(tmp_path) == tmp_path

    def test_finds_from_subdirectory(self, workspace: Path):
        sub = workspace / "github" / "owner" / "repo"
        sub.mkdir(parents=True)
        assert find_root(sub) == workspace

    def test_raises_if_not_found(self, tmp_path: Path):
        with pytest.raises(SystemExit, match="not inside a reporoot"):
            find_root(tmp_path)


class TestActiveProject:
    def test_no_active_file(self, workspace: Path):
        assert active_project(workspace) is None

    def test_empty_active_file(self, workspace: Path):
        (workspace / ".reporoot-active").write_text("")
        assert active_project(workspace) is None

    def test_valid_active_project(self, workspace: Path):
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (workspace / ".reporoot-active").write_text("myproject\n")
        assert active_project(workspace) == "myproject"

    def test_invalid_project_warns(self, workspace: Path, capsys):
        (workspace / ".reporoot-active").write_text("nonexistent\n")
        assert active_project(workspace) is None
        captured = capsys.readouterr()
        assert "does not exist" in captured.out

    def test_multi_segment_active_project(self, workspace: Path):
        project_dir = workspace / "projects" / "chatly" / "web-app"
        project_dir.mkdir(parents=True)
        (workspace / ".reporoot-active").write_text("chatly/web-app\n")
        assert active_project(workspace) == "chatly/web-app"

    def test_require_active_raises(self, workspace: Path):
        with pytest.raises(SystemExit, match="no active project"):
            require_active_project(workspace)


class TestProjectReposFile:
    def test_simple_project(self, workspace: Path):
        result = project_repos_file(workspace, "alpha")
        assert result == workspace / "projects" / "alpha" / "alpha.repos"

    def test_multi_segment_project(self, workspace: Path):
        result = project_repos_file(workspace, "chatly/web-app")
        assert result == workspace / "projects" / "chatly" / "web-app" / "web-app.repos"

    def test_lock_file_simple(self, workspace: Path):
        result = project_lock_file(workspace, "alpha")
        assert result == workspace / "projects" / "alpha" / "alpha.lock.repos"

    def test_lock_file_multi_segment(self, workspace: Path):
        result = project_lock_file(workspace, "chatly/web-app")
        assert result == workspace / "projects" / "chatly" / "web-app" / "web-app.lock.repos"


class TestAllProjectReposFiles:
    def test_finds_project_repos(self, workspace: Path):
        p1 = workspace / "projects" / "alpha"
        p1.mkdir(parents=True)
        (p1 / "alpha.repos").write_text("repositories:\n")

        p2 = workspace / "projects" / "beta"
        p2.mkdir(parents=True)
        (p2 / "beta.repos").write_text("repositories:\n")

        result = all_project_repos_files(workspace)
        assert len(result) == 2
        assert result[0][0] == "alpha"
        assert result[1][0] == "beta"

    def test_skips_projects_without_repos_file(self, workspace: Path):
        p = workspace / "projects" / "nofile"
        p.mkdir(parents=True)
        assert all_project_repos_files(workspace) == []

    def test_finds_nested_projects(self, workspace: Path):
        # Top-level project
        p1 = workspace / "projects" / "alpha"
        p1.mkdir(parents=True)
        (p1 / "alpha.repos").write_text("repositories:\n")

        # Nested project
        p2 = workspace / "projects" / "chatly" / "web-app"
        p2.mkdir(parents=True)
        (p2 / "web-app.repos").write_text("repositories:\n")

        result = all_project_repos_files(workspace)
        assert len(result) == 2
        assert result[0][0] == "alpha"
        assert result[1][0] == "chatly/web-app"

    def test_skips_lock_repos(self, workspace: Path):
        p = workspace / "projects" / "alpha"
        p.mkdir(parents=True)
        (p / "alpha.repos").write_text("repositories:\n")
        (p / "alpha.lock.repos").write_text("repositories:\n")

        result = all_project_repos_files(workspace)
        assert len(result) == 1
        assert result[0][0] == "alpha"


class TestAllKnownRepos:
    def test_union_of_projects(self, workspace: Path):
        p1 = workspace / "projects" / "alpha"
        p1.mkdir(parents=True)
        (p1 / "alpha.repos").write_text(
            "repositories:\n"
            "  github/a/shared:\n"
            "    type: git\n"
            "    url: https://github.com/a/shared.git\n"
            "    version: main\n"
            "  github/a/only-alpha:\n"
            "    type: git\n"
            "    url: https://github.com/a/only-alpha.git\n"
            "    version: main\n"
        )

        p2 = workspace / "projects" / "beta"
        p2.mkdir(parents=True)
        (p2 / "beta.repos").write_text(
            "repositories:\n"
            "  github/a/shared:\n"
            "    type: git\n"
            "    url: https://github.com/a/shared.git\n"
            "    version: main\n"
            "  github/b/only-beta:\n"
            "    type: git\n"
            "    url: https://github.com/b/only-beta.git\n"
            "    version: main\n"
        )

        known = all_known_repos(workspace)
        assert known == {"github/a/shared", "github/a/only-alpha", "github/b/only-beta"}


class TestParseGithubUrl:
    def test_https(self):
        assert parse_github_url("https://github.com/owner/repo.git") == ("owner", "repo")

    def test_https_no_git(self):
        assert parse_github_url("https://github.com/owner/repo") == ("owner", "repo")

    def test_ssh(self):
        assert parse_github_url("git@github.com:owner/repo.git") == ("owner", "repo")

    def test_ssh_no_git(self):
        assert parse_github_url("git@github.com:owner/repo") == ("owner", "repo")

    def test_trailing_slash(self):
        assert parse_github_url("https://github.com/owner/repo/") == ("owner", "repo")

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="unknown registry host"):
            parse_github_url("https://unknown.example.com/owner/repo")


class TestNormalizeGithubUrl:
    def test_basic(self):
        assert normalize_github_url("owner", "repo") == "https://github.com/owner/repo.git"


class TestReadRepos:
    def test_reads_repos(self, tmp_path: Path):
        f = tmp_path / "test.repos"
        f.write_text(
            "repositories:\n"
            "  github/owner/repo:\n"
            "    type: git\n"
            "    url: https://github.com/owner/repo.git\n"
            "    version: main\n"
        )
        repos = read_repos(f)
        assert "github/owner/repo" in repos
        assert repos["github/owner/repo"]["url"] == "https://github.com/owner/repo.git"

    def test_missing_file(self, tmp_path: Path):
        assert read_repos(tmp_path / "missing.repos") == {}

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.repos"
        f.write_text("")
        assert read_repos(f) == {}

    def test_empty_repositories(self, tmp_path: Path):
        f = tmp_path / "empty.repos"
        f.write_text("repositories:\n")
        assert read_repos(f) == {}


class TestAppendEntry:
    def test_creates_file(self, tmp_path: Path):
        f = tmp_path / "new.repos"
        append_entry(f, "github/owner/repo", "https://github.com/owner/repo.git", "main")
        content = f.read_text()
        assert "repositories:" in content
        assert "github/owner/repo:" in content
        assert "url: https://github.com/owner/repo.git" in content

    def test_appends_to_existing(self, tmp_path: Path):
        f = tmp_path / "existing.repos"
        f.write_text(
            "repositories:\n  github/a/b:\n    type: git\n    url: https://github.com/a/b.git\n    version: main\n"
        )
        append_entry(f, "github/c/d", "https://github.com/c/d.git", "main")
        repos = read_repos(f)
        assert "github/a/b" in repos
        assert "github/c/d" in repos

    def test_skips_duplicate(self, tmp_path: Path, capsys):
        f = tmp_path / "dup.repos"
        f.write_text(
            "repositories:\n  github/a/b:\n    type: git\n    url: https://github.com/a/b.git\n    version: main\n"
        )
        append_entry(f, "github/a/b", "https://github.com/a/b.git", "main")
        captured = capsys.readouterr()
        assert "already present" in captured.out

    def test_role_field(self, tmp_path: Path):
        f = tmp_path / "role.repos"
        append_entry(
            f,
            "github/a/b",
            "https://github.com/a/b.git",
            "main",
            role="primary",
            note="our code",
        )
        content = f.read_text()
        assert "    role: primary" in content
        assert "# our code" in content
        # role should be a YAML field, not a comment
        repos = read_repos(f)
        assert repos["github/a/b"]["role"] == "primary"
