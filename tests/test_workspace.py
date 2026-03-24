"""Tests for rr.workspace — root finding, URL parsing, reporoot.yaml I/O, workspace management."""

from __future__ import annotations

from pathlib import Path

import pytest

from reporoot.workspace import (
    _is_workspace_dir,
    all_known_repos,
    all_project_repos_files,
    append_entry,
    bare_repo_path,
    create_workspace,
    delete_workspace,
    find_root,
    infer_context,
    list_workspaces,
    normalize_github_url,
    parse_github_url,
    project_lock_file,
    project_repos_file,
    read_repos,
    sync_workspace,
    workspace_dir,
)


class TestFindRoot:
    def test_finds_by_github_dir(self, tmp_path: Path):
        (tmp_path / "github").mkdir()
        assert find_root(tmp_path) == tmp_path

    def test_finds_by_projects_dir(self, tmp_path: Path):
        (tmp_path / "projects").mkdir()
        assert find_root(tmp_path) == tmp_path

    def test_finds_from_subdirectory(self, workspace: Path):
        sub = workspace / "github" / "owner" / "repo"
        sub.mkdir(parents=True)
        assert find_root(sub) == workspace

    def test_raises_if_not_found(self, tmp_path: Path):
        with pytest.raises(SystemExit, match="not inside a reporoot"):
            find_root(tmp_path)


class TestProjectReposFile:
    def test_simple_project(self, workspace: Path):
        result = project_repos_file(workspace, "alpha")
        assert result == workspace / "projects" / "alpha" / "reporoot.yaml"

    def test_multi_segment_project(self, workspace: Path):
        result = project_repos_file(workspace, "chatly/web-app")
        assert result == workspace / "projects" / "chatly" / "web-app" / "reporoot.yaml"

    def test_lock_file_simple(self, workspace: Path):
        result = project_lock_file(workspace, "alpha")
        assert result == workspace / "projects" / "alpha" / "reporoot.lock"

    def test_lock_file_multi_segment(self, workspace: Path):
        result = project_lock_file(workspace, "chatly/web-app")
        assert result == workspace / "projects" / "chatly" / "web-app" / "reporoot.lock"


class TestAllProjectReposFiles:
    def test_finds_project_repos(self, workspace: Path):
        p1 = workspace / "projects" / "alpha"
        p1.mkdir(parents=True)
        (p1 / "reporoot.yaml").write_text("repositories:\n")

        p2 = workspace / "projects" / "beta"
        p2.mkdir(parents=True)
        (p2 / "reporoot.yaml").write_text("repositories:\n")

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
        (p1 / "reporoot.yaml").write_text("repositories:\n")

        # Nested project
        p2 = workspace / "projects" / "chatly" / "web-app"
        p2.mkdir(parents=True)
        (p2 / "reporoot.yaml").write_text("repositories:\n")

        result = all_project_repos_files(workspace)
        assert len(result) == 2
        assert result[0][0] == "alpha"
        assert result[1][0] == "chatly/web-app"

    def test_skips_lock_repos(self, workspace: Path):
        p = workspace / "projects" / "alpha"
        p.mkdir(parents=True)
        (p / "reporoot.yaml").write_text("repositories:\n")
        (p / "reporoot.lock").write_text("repositories:\n")

        result = all_project_repos_files(workspace)
        assert len(result) == 1
        assert result[0][0] == "alpha"


class TestAllKnownRepos:
    def test_union_of_projects(self, workspace: Path):
        p1 = workspace / "projects" / "alpha"
        p1.mkdir(parents=True)
        (p1 / "reporoot.yaml").write_text(
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
        (p2 / "reporoot.yaml").write_text(
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
        with pytest.raises(ValueError, match="cannot parse"):
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


# --- Workspace management tests ---


class TestIsWorkspaceDir:
    def test_workspace_dir(self, tmp_path: Path):
        ws = tmp_path / "projects" / "myproject" / "workspaces" / "default"
        ws.mkdir(parents=True)
        assert _is_workspace_dir(ws)

    def test_not_workspace_plain_dir(self, tmp_path: Path):
        d = tmp_path / "github" / "owner"
        d.mkdir(parents=True)
        assert not _is_workspace_dir(d)

    def test_not_workspace_workspaces_without_projects(self, tmp_path: Path):
        d = tmp_path / "workspaces" / "default"
        d.mkdir(parents=True)
        assert not _is_workspace_dir(d)

    def test_nested_project_workspace(self, tmp_path: Path):
        ws = tmp_path / "projects" / "chatly" / "web-app" / "workspaces" / "agent-1"
        ws.mkdir(parents=True)
        assert _is_workspace_dir(ws)


class TestFindRootWorkspace:
    def test_skips_workspace_github_dir(self, tmp_path: Path):
        """find_root should not match a workspace's github/ dir as root."""
        root = tmp_path / "root"
        (root / "projects" / "myproject" / "workspaces" / "default" / "github" / "owner" / "repo").mkdir(parents=True)
        # The real root has projects/
        deep = root / "projects" / "myproject" / "workspaces" / "default" / "github" / "owner" / "repo"
        assert find_root(deep) == root

    def test_still_finds_root_with_github(self, tmp_path: Path):
        """Standalone github/ dir still works as root marker."""
        (tmp_path / "github").mkdir()
        assert find_root(tmp_path) == tmp_path


class TestWorkspacePaths:
    def test_workspace_dir(self, workspace: Path):
        result = workspace_dir(workspace, "myproject", "default")
        assert result == workspace / "projects" / "myproject" / "workspaces" / "default"

    def test_workspace_dir_default_name(self, workspace: Path):
        result = workspace_dir(workspace, "myproject")
        assert result == workspace / "projects" / "myproject" / "workspaces" / "default"

    def test_bare_repo_path(self, workspace: Path):
        result = bare_repo_path(workspace, "github/owner/repo")
        assert result == workspace / "github" / "owner" / "repo.git"

    def test_bare_repo_path_deep(self, workspace: Path):
        result = bare_repo_path(workspace, "gitlab/org/sub/repo")
        assert result == workspace / "gitlab" / "org" / "sub" / "repo.git"


class TestListWorkspaces:
    def test_no_workspaces_dir(self, workspace: Path):
        (workspace / "projects" / "myproject").mkdir(parents=True)
        assert list_workspaces(workspace, "myproject") == []

    def test_lists_workspace_dirs(self, workspace: Path):
        ws_parent = workspace / "projects" / "myproject" / "workspaces"
        (ws_parent / "default").mkdir(parents=True)
        (ws_parent / "agent-1").mkdir(parents=True)
        assert list_workspaces(workspace, "myproject") == ["agent-1", "default"]

    def test_ignores_files(self, workspace: Path):
        ws_parent = workspace / "projects" / "myproject" / "workspaces"
        ws_parent.mkdir(parents=True)
        (ws_parent / ".gitkeep").write_text("")
        (ws_parent / "default").mkdir()
        assert list_workspaces(workspace, "myproject") == ["default"]


class TestInferContext:
    def test_from_workspace(self, workspace: Path):
        ws = workspace / "projects" / "myproject" / "workspaces" / "default"
        ws.mkdir(parents=True)
        (workspace / "projects" / "myproject" / "reporoot.yaml").write_text("repositories:\n")
        ctx = infer_context(ws)
        assert ctx.root == workspace
        assert ctx.project == "myproject"
        assert ctx.workspace == "default"

    def test_from_deep_in_workspace(self, workspace: Path):
        repo = workspace / "projects" / "myproject" / "workspaces" / "default" / "github" / "owner" / "repo"
        repo.mkdir(parents=True)
        (workspace / "projects" / "myproject" / "reporoot.yaml").write_text("repositories:\n")
        ctx = infer_context(repo)
        assert ctx.root == workspace
        assert ctx.project == "myproject"
        assert ctx.workspace == "default"

    def test_from_project_dir(self, workspace: Path):
        project_dir = workspace / "projects" / "myproject"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text("repositories:\n")
        ctx = infer_context(project_dir)
        assert ctx.root == workspace
        assert ctx.project == "myproject"
        assert ctx.workspace is None

    def test_from_project_subdir(self, workspace: Path):
        docs = workspace / "projects" / "myproject" / "docs"
        docs.mkdir(parents=True)
        (workspace / "projects" / "myproject" / "reporoot.yaml").write_text("repositories:\n")
        ctx = infer_context(docs)
        assert ctx.project == "myproject"
        assert ctx.workspace is None

    def test_from_outside_projects(self, workspace: Path):
        repo = workspace / "github" / "owner" / "repo"
        repo.mkdir(parents=True)
        ctx = infer_context(repo)
        assert ctx.root == workspace
        assert ctx.project is None
        assert ctx.workspace is None

    def test_multi_segment_project(self, workspace: Path):
        ws = workspace / "projects" / "chatly" / "web-app" / "workspaces" / "agent-1"
        ws.mkdir(parents=True)
        ctx = infer_context(ws)
        assert ctx.project == "chatly/web-app"
        assert ctx.workspace == "agent-1"

    def test_projects_dir_itself(self, workspace: Path):
        ctx = infer_context(workspace / "projects")
        assert ctx.project is None
        assert ctx.workspace is None


class TestCreateWorkspace:
    def test_creates_worktrees(self, workspace: Path, bare_repo: Path):
        # Set up project with bare repo
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)

        # Move bare repo into workspace store
        store = workspace / "github" / "test-owner" / "test-repo.git"
        store.parent.mkdir(parents=True)
        bare_repo.rename(store)

        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/test-owner/test-repo:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/test-repo.git\n"
            "    version: main\n"
        )

        ws = create_workspace(workspace, "test-project", "default")
        assert ws.exists()
        assert (ws / "github" / "test-owner" / "test-repo" / "README.md").exists()
        # .git is a file in worktrees
        assert (ws / "github" / "test-owner" / "test-repo" / ".git").is_file()

    def test_already_exists(self, workspace: Path):
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text("repositories:\n")
        ws = workspace / "projects" / "test-project" / "workspaces" / "default"
        ws.mkdir(parents=True)
        with pytest.raises(SystemExit, match="already exists"):
            create_workspace(workspace, "test-project", "default")

    def test_no_manifest(self, workspace: Path):
        with pytest.raises(SystemExit, match="no reporoot.yaml"):
            create_workspace(workspace, "nonexistent", "default")

    def test_missing_bare_repo(self, workspace: Path):
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)
        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/owner/missing:\n"
            "    type: git\n"
            "    url: https://github.com/owner/missing.git\n"
            "    version: main\n"
        )
        with pytest.raises(SystemExit, match="bare repo not found"):
            create_workspace(workspace, "test-project", "default")


class TestDeleteWorkspace:
    def test_deletes_worktrees_and_dir(self, workspace: Path, bare_repo: Path):
        # Set up workspace with a worktree
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)

        store = workspace / "github" / "test-owner" / "test-repo.git"
        store.parent.mkdir(parents=True)
        bare_repo.rename(store)

        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/test-owner/test-repo:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/test-repo.git\n"
            "    version: main\n"
        )

        ws = create_workspace(workspace, "test-project", "to-delete")
        assert ws.exists()

        delete_workspace(workspace, "test-project", "to-delete")
        assert not ws.exists()

    def test_not_found(self, workspace: Path):
        (workspace / "projects" / "test-project").mkdir(parents=True)
        with pytest.raises(SystemExit, match="not found"):
            delete_workspace(workspace, "test-project", "nonexistent")


class TestSyncWorkspace:
    def test_adds_missing_worktree(self, workspace: Path, bare_repo: Path, git_repo: Path):
        # Set up with one repo
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)

        store = workspace / "github" / "test-owner" / "test-repo.git"
        store.parent.mkdir(parents=True)
        bare_repo.rename(store)

        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/test-owner/test-repo:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/test-repo.git\n"
            "    version: main\n"
        )

        ws = create_workspace(workspace, "test-project", "sync-test")

        # Add a second repo to manifest after workspace creation
        import subprocess

        second_bare = workspace / "github" / "test-owner" / "second.git"
        second_bare.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--bare", str(git_repo), str(second_bare)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(second_bare), "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"],
            capture_output=True,
            check=True,
        )
        subprocess.run(["git", "-C", str(second_bare), "fetch", "origin"], capture_output=True, check=True)

        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/test-owner/test-repo:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/test-repo.git\n"
            "    version: main\n"
            "  github/test-owner/second:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/second.git\n"
            "    version: main\n"
        )

        sync_workspace(workspace, "test-project", "sync-test")
        assert (ws / "github" / "test-owner" / "second" / "README.md").exists()

    def test_already_in_sync(self, workspace: Path, bare_repo: Path, capsys):
        project_dir = workspace / "projects" / "test-project"
        project_dir.mkdir(parents=True)

        store = workspace / "github" / "test-owner" / "test-repo.git"
        store.parent.mkdir(parents=True)
        bare_repo.rename(store)

        (project_dir / "reporoot.yaml").write_text(
            "repositories:\n"
            "  github/test-owner/test-repo:\n"
            "    type: git\n"
            "    url: https://github.com/test-owner/test-repo.git\n"
            "    version: main\n"
        )

        create_workspace(workspace, "test-project", "sync-test")
        sync_workspace(workspace, "test-project", "sync-test")
        captured = capsys.readouterr()
        assert "in sync" in captured.out

    def test_not_found(self, workspace: Path):
        (workspace / "projects" / "test-project").mkdir(parents=True)
        with pytest.raises(SystemExit, match="not found"):
            sync_workspace(workspace, "test-project", "nonexistent")
