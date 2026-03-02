"""Tests for reporoot config — registry configuration and URL parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from reporoot.config import (
    domain_to_registry,
    normalize_repo_url,
    parse_repo_url,
    registry_names,
    registry_to_domain,
    resolve_shorthand,
    url_to_local_path,
)


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

    def test_trailing_slash(self):
        assert parse_repo_url("https://github.com/owner/repo/") == ("github", "owner", "repo")

    def test_unknown_host_raises(self):
        with pytest.raises(ValueError, match="unknown registry host"):
            parse_repo_url("https://unknown.example.com/owner/repo.git")


class TestNormalizeRepoUrl:
    def test_github(self):
        assert normalize_repo_url("github", "owner", "repo") == "https://github.com/owner/repo.git"

    def test_gitlab(self):
        assert normalize_repo_url("gitlab", "owner", "repo") == "https://gitlab.com/owner/repo.git"


class TestUrlToLocalPath:
    def test_github(self):
        assert url_to_local_path("https://github.com/foo/bar.git") == "github/foo/bar"

    def test_gitlab(self):
        assert url_to_local_path("https://gitlab.com/foo/bar.git") == "gitlab/foo/bar"


class TestResolveShorthand:
    def test_owner_repo(self):
        url, path = resolve_shorthand("cwalv/agent-relay")
        assert url == "https://github.com/cwalv/agent-relay.git"
        assert path == "github/cwalv/agent-relay"

    def test_registry_owner_repo(self):
        url, path = resolve_shorthand("gitlab/myorg/myrepo")
        assert url == "https://gitlab.com/myorg/myrepo.git"
        assert path == "gitlab/myorg/myrepo"

    def test_unknown_registry_raises(self):
        with pytest.raises(ValueError, match="unknown registry"):
            resolve_shorthand("nonexistent/owner/repo")

    def test_single_segment_raises(self):
        with pytest.raises(ValueError, match="expected"):
            resolve_shorthand("justarepo")


class TestCustomRegistry:
    def test_custom_from_config(self, tmp_path: Path, monkeypatch):
        """Custom registries from config file should be recognized."""
        config_dir = tmp_path / "config" / "reporoot"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text("registries:\n  internal: git.mycompany.com\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

        # Should now recognize the custom domain
        assert domain_to_registry("git.mycompany.com") == "internal"
        assert parse_repo_url("https://git.mycompany.com/team/service.git") == ("internal", "team", "service")
        assert url_to_local_path("https://git.mycompany.com/team/service.git") == "internal/team/service"
