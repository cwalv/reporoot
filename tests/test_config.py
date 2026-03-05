"""Tests for reporoot config — registry configuration and URL parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from reporoot.config import (
    DirectoryRegistry,
    DomainRegistry,
    domain_to_registry,
    normalize_repo_url,
    parse_repo_url,
    registry_names,
    registry_to_domain,
    resolve_shorthand,
    url_to_local_path,
)

# ---------------------------------------------------------------------------
# DomainRegistry
# ---------------------------------------------------------------------------


class TestDomainRegistry:
    def test_matches_https(self):
        r = DomainRegistry("github", "github.com")
        assert r.matches_url("https://github.com/owner/repo.git")

    def test_matches_ssh(self):
        r = DomainRegistry("github", "github.com")
        assert r.matches_url("git@github.com:owner/repo.git")

    def test_matches_www(self):
        r = DomainRegistry("github", "github.com")
        assert r.matches_url("https://www.github.com/owner/repo.git")

    def test_no_match_different_host(self):
        r = DomainRegistry("github", "github.com")
        assert not r.matches_url("https://gitlab.com/owner/repo.git")

    def test_no_match_file_url(self):
        r = DomainRegistry("github", "github.com")
        assert not r.matches_url("file:///tmp/repos/owner/repo.git")

    def test_parse_https(self):
        r = DomainRegistry("github", "github.com")
        assert r.parse_url("https://github.com/owner/repo.git") == ("owner", "repo")

    def test_parse_https_no_git_suffix(self):
        r = DomainRegistry("github", "github.com")
        assert r.parse_url("https://github.com/owner/repo") == ("owner", "repo")

    def test_parse_ssh(self):
        r = DomainRegistry("github", "github.com")
        assert r.parse_url("git@github.com:owner/repo.git") == ("owner", "repo")

    def test_parse_trailing_slash(self):
        r = DomainRegistry("github", "github.com")
        assert r.parse_url("https://github.com/owner/repo/") == ("owner", "repo")

    def test_normalize(self):
        r = DomainRegistry("github", "github.com")
        assert r.normalize_url("owner", "repo") == "https://github.com/owner/repo.git"

    def test_bitbucket_https(self):
        r = DomainRegistry("bitbucket", "bitbucket.org")
        assert r.matches_url("https://bitbucket.org/team/project.git")
        assert r.parse_url("https://bitbucket.org/team/project.git") == ("team", "project")
        assert r.normalize_url("team", "project") == "https://bitbucket.org/team/project.git"

    def test_bitbucket_ssh(self):
        r = DomainRegistry("bitbucket", "bitbucket.org")
        assert r.matches_url("git@bitbucket.org:team/project.git")
        assert r.parse_url("git@bitbucket.org:team/project.git") == ("team", "project")


# ---------------------------------------------------------------------------
# DirectoryRegistry
# ---------------------------------------------------------------------------


class TestDirectoryRegistry:
    def test_matches_file_url(self):
        r = DirectoryRegistry("local", "/tmp/repos")
        assert r.matches_url("file:///tmp/repos/owner/repo.git")

    def test_no_match_different_path(self):
        r = DirectoryRegistry("local", "/tmp/repos")
        assert not r.matches_url("file:///other/path/owner/repo.git")

    def test_no_match_https(self):
        r = DirectoryRegistry("local", "/tmp/repos")
        assert not r.matches_url("https://github.com/owner/repo.git")

    def test_parse(self):
        r = DirectoryRegistry("local", "/tmp/repos")
        assert r.parse_url("file:///tmp/repos/owner/repo.git") == ("owner", "repo")

    def test_parse_no_git_suffix(self):
        r = DirectoryRegistry("local", "/tmp/repos")
        assert r.parse_url("file:///tmp/repos/owner/repo") == ("owner", "repo")

    def test_parse_trailing_slash_on_base(self):
        r = DirectoryRegistry("local", "/tmp/repos/")
        assert r.parse_url("file:///tmp/repos/owner/repo.git") == ("owner", "repo")

    def test_parse_missing_owner_raises(self):
        r = DirectoryRegistry("local", "/tmp/repos")
        with pytest.raises(ValueError, match="cannot parse"):
            r.parse_url("file:///tmp/repos/repo.git")

    def test_normalize(self):
        r = DirectoryRegistry("local", "/tmp/repos")
        assert r.normalize_url("owner", "repo") == "file:///tmp/repos/owner/repo.git"

    def test_no_match_partial_prefix(self):
        """file:///tmp/repos-other/ should not match /tmp/repos."""
        r = DirectoryRegistry("local", "/tmp/repos")
        assert not r.matches_url("file:///tmp/repos-other/owner/repo.git")


# ---------------------------------------------------------------------------
# Built-in registries (via public API)
# ---------------------------------------------------------------------------


class TestBuiltinRegistries:
    def test_github(self):
        assert domain_to_registry("github.com") == "github"

    def test_gitlab(self):
        assert domain_to_registry("gitlab.com") == "gitlab"

    def test_bitbucket(self):
        assert domain_to_registry("bitbucket.org") == "bitbucket"

    def test_www_prefix(self):
        assert domain_to_registry("www.github.com") == "github"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="unknown registry host"):
            domain_to_registry("unknown.example.com")

    def test_registry_names(self):
        names = registry_names()
        assert "github" in names
        assert "gitlab" in names
        assert "bitbucket" in names


class TestReverseLookup:
    def test_github(self):
        assert registry_to_domain("github") == "github.com"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="unknown registry"):
            registry_to_domain("nonexistent")


class TestParseRepoUrl:
    def test_github_https(self):
        assert parse_repo_url("https://github.com/owner/repo.git") == ("github", "owner", "repo")

    def test_github_https_no_git(self):
        assert parse_repo_url("https://github.com/owner/repo") == ("github", "owner", "repo")

    def test_github_ssh(self):
        assert parse_repo_url("git@github.com:owner/repo.git") == ("github", "owner", "repo")

    def test_gitlab_https(self):
        assert parse_repo_url("https://gitlab.com/owner/repo.git") == ("gitlab", "owner", "repo")

    def test_gitlab_ssh(self):
        assert parse_repo_url("git@gitlab.com:owner/repo.git") == ("gitlab", "owner", "repo")

    def test_bitbucket_https(self):
        assert parse_repo_url("https://bitbucket.org/owner/repo.git") == ("bitbucket", "owner", "repo")

    def test_bitbucket_ssh(self):
        assert parse_repo_url("git@bitbucket.org:owner/repo.git") == ("bitbucket", "owner", "repo")

    def test_trailing_slash(self):
        assert parse_repo_url("https://github.com/owner/repo/") == ("github", "owner", "repo")

    def test_unknown_host_raises(self):
        with pytest.raises(ValueError, match="cannot parse"):
            parse_repo_url("https://unknown.example.com/owner/repo.git")

    def test_file_url_without_config_raises(self):
        with pytest.raises(ValueError, match="cannot parse"):
            parse_repo_url("file:///tmp/repos/owner/repo.git")

    def test_file_url_with_config(self, tmp_path: Path, monkeypatch):
        config_dir = tmp_path / "config" / "reporoot"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text("registries:\n  local: /tmp/repos\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        assert parse_repo_url("file:///tmp/repos/owner/repo.git") == ("local", "owner", "repo")


class TestNormalizeRepoUrl:
    def test_github(self):
        assert normalize_repo_url("github", "owner", "repo") == "https://github.com/owner/repo.git"

    def test_gitlab(self):
        assert normalize_repo_url("gitlab", "owner", "repo") == "https://gitlab.com/owner/repo.git"

    def test_bitbucket(self):
        assert normalize_repo_url("bitbucket", "team", "proj") == "https://bitbucket.org/team/proj.git"

    def test_directory_registry(self, tmp_path: Path, monkeypatch):
        config_dir = tmp_path / "config" / "reporoot"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text("registries:\n  local: /srv/repos\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        assert normalize_repo_url("local", "owner", "repo") == "file:///srv/repos/owner/repo.git"


class TestUrlToLocalPath:
    def test_github(self):
        assert url_to_local_path("https://github.com/foo/bar.git") == "github/foo/bar"

    def test_gitlab(self):
        assert url_to_local_path("https://gitlab.com/foo/bar.git") == "gitlab/foo/bar"

    def test_bitbucket(self):
        assert url_to_local_path("https://bitbucket.org/team/proj.git") == "bitbucket/team/proj"


class TestResolveShorthand:
    def test_owner_repo(self):
        url, path = resolve_shorthand("cwalv/agent-relay")
        assert url == "https://github.com/cwalv/agent-relay.git"
        assert path == "github/cwalv/agent-relay"

    def test_registry_owner_repo(self):
        url, path = resolve_shorthand("gitlab/myorg/myrepo")
        assert url == "https://gitlab.com/myorg/myrepo.git"
        assert path == "gitlab/myorg/myrepo"

    def test_bitbucket_shorthand(self):
        url, path = resolve_shorthand("bitbucket/team/proj")
        assert url == "https://bitbucket.org/team/proj.git"
        assert path == "bitbucket/team/proj"

    def test_unknown_registry_raises(self):
        with pytest.raises(ValueError, match="unknown registry"):
            resolve_shorthand("nonexistent/owner/repo")

    def test_single_segment_raises(self):
        with pytest.raises(ValueError, match="expected"):
            resolve_shorthand("justarepo")


class TestCustomRegistry:
    def test_custom_domain_from_config(self, tmp_path: Path, monkeypatch):
        """Custom domain registries from config file should be recognized."""
        config_dir = tmp_path / "config" / "reporoot"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text("registries:\n  internal: git.mycompany.com\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        assert domain_to_registry("git.mycompany.com") == "internal"
        assert parse_repo_url("https://git.mycompany.com/team/service.git") == ("internal", "team", "service")
        assert url_to_local_path("https://git.mycompany.com/team/service.git") == "internal/team/service"

    def test_custom_directory_from_config(self, tmp_path: Path, monkeypatch):
        """Directory registries from config file should be recognized."""
        config_dir = tmp_path / "config" / "reporoot"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text("registries:\n  local: /srv/git\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        assert "local" in registry_names()
        assert parse_repo_url("file:///srv/git/team/service.git") == ("local", "team", "service")
        assert normalize_repo_url("local", "team", "service") == "file:///srv/git/team/service.git"
        assert url_to_local_path("file:///srv/git/team/service.git") == "local/team/service"
