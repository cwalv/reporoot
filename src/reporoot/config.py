"""Registry configuration — mapping URLs to local directory names.

Reads ~/.config/reporoot/config.yaml (or $XDG_CONFIG_HOME/reporoot/config.yaml).
Well-known hosts have built-in defaults; only custom registries need configuration.

A registry has a name and knows how to resolve owners and repos from URLs.
Two kinds:
- Domain-based: github.com → github/ (handles https:// and git@ URLs)
- Directory-based: /path/to/repos → local/ (handles file:// URLs)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse


class Registry(Protocol):
    """Something we can fetch from.  Has a name, resolves owners and repos."""

    @property
    def name(self) -> str: ...

    def matches_url(self, url: str) -> bool:
        """Does this registry handle the given URL?"""
        ...

    def parse_url(self, url: str) -> tuple[str, str]:
        """Extract (owner, repo) from a URL this registry handles."""
        ...

    def normalize_url(self, owner: str, repo: str) -> str:
        """Construct the canonical clone URL for owner/repo."""
        ...


class DomainRegistry:
    """Registry backed by a hostname (e.g., github.com → github)."""

    def __init__(self, name: str, domain: str):
        self._name = name
        self.domain = domain

    @property
    def name(self) -> str:
        return self._name

    def matches_url(self, url: str) -> bool:
        url = url.rstrip("/")

        # SSH: git@host:...
        ssh_match = re.match(r"git@([^:]+):", url)
        if ssh_match:
            return self._domain_matches(ssh_match.group(1))

        # HTTPS: https://host/...
        parsed = urlparse(url)
        if parsed.hostname:
            return self._domain_matches(parsed.hostname)

        return False

    def _domain_matches(self, host: str) -> bool:
        return host == self.domain or host.removeprefix("www.") == self.domain

    def parse_url(self, url: str) -> tuple[str, str]:
        url = url.rstrip("/")

        # SSH: git@host:owner/repo.git
        ssh_match = re.match(r"git@[^:]+:(.+?)/(.+?)(?:\.git)?$", url)
        if ssh_match:
            return ssh_match.group(1), ssh_match.group(2)

        # HTTPS: https://host/owner/repo.git
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[0], parts[1].removesuffix(".git")

        raise ValueError(f"cannot parse owner/repo from URL: {url}")

    def normalize_url(self, owner: str, repo: str) -> str:
        return f"https://{self.domain}/{owner}/{repo}.git"


class DirectoryRegistry:
    """Registry backed by a local directory (handles file:// URLs)."""

    def __init__(self, name: str, path: str):
        self._name = name
        self.path = path.rstrip("/")

    @property
    def name(self) -> str:
        return self._name

    def matches_url(self, url: str) -> bool:
        if not url.startswith("file://"):
            return False
        file_path = url[len("file://") :].rstrip("/")
        return file_path.startswith(self.path + "/")

    def parse_url(self, url: str) -> tuple[str, str]:
        file_path = url[len("file://") :].rstrip("/").removesuffix(".git")
        remainder = file_path[len(self.path) :].strip("/")
        parts = remainder.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        raise ValueError(f"cannot parse owner/repo from file URL: {url}")

    def normalize_url(self, owner: str, repo: str) -> str:
        return f"file://{self.path}/{owner}/{repo}.git"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def config_dir() -> Path:
    """XDG-compliant config directory for reporoot."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "reporoot"


def load_config() -> dict:
    """Load config.yaml, returning empty dict if not found."""
    import yaml

    config_file = config_dir() / "config.yaml"
    if not config_file.exists():
        return {}
    with open(config_file) as f:
        data = yaml.safe_load(f)
    return data or {}


# Built-in registries
_BUILTIN: list[DomainRegistry] = [
    DomainRegistry("github", "github.com"),
    DomainRegistry("gitlab", "gitlab.com"),
    DomainRegistry("bitbucket", "bitbucket.org"),
]


def _all_registries() -> list[DomainRegistry | DirectoryRegistry]:
    """Return all known registries (built-in + user config)."""
    result: list[DomainRegistry | DirectoryRegistry] = list(_BUILTIN)
    config = load_config()
    for name, value in config.get("registries", {}).items():
        if value.startswith("/"):
            result.append(DirectoryRegistry(name, value))
        else:
            result.append(DomainRegistry(name, value))
    return result


def find_registry(name: str) -> DomainRegistry | DirectoryRegistry:
    """Look up a registry by short name. Raises ValueError if unknown."""
    for r in _all_registries():
        if r.name == name:
            return r
    raise ValueError(f"unknown registry: {name}")


# ---------------------------------------------------------------------------
# Public API — delegates to registries
# ---------------------------------------------------------------------------


def registry_names() -> set[str]:
    """Return the set of all known registry short names."""
    return {r.name for r in _all_registries()}


def parse_repo_url(url: str) -> tuple[str, str, str]:
    """Extract (registry, owner, repo) from a git URL.

    Tries each registered registry in order.  Raises ValueError if no
    registry matches.

    Examples:
    - https://github.com/owner/repo.git -> ("github", "owner", "repo")
    - git@gitlab.com:owner/repo.git -> ("gitlab", "owner", "repo")
    - file:///path/to/repos/owner/repo.git -> ("local", "owner", "repo")
      (if /path/to/repos is registered as "local")
    """
    for r in _all_registries():
        if r.matches_url(url):
            owner, repo = r.parse_url(url)
            return r.name, owner, repo
    raise ValueError(f"cannot parse registry/owner/repo from URL: {url} (configure in {config_dir() / 'config.yaml'})")


def normalize_repo_url(registry: str, owner: str, repo: str) -> str:
    """Canonical clone URL for a registry/owner/repo triple."""
    return find_registry(registry).normalize_url(owner, repo)


def url_to_local_path(url: str) -> str:
    """URL -> local path. e.g. https://github.com/foo/bar.git -> github/foo/bar"""
    registry, owner, repo = parse_repo_url(url)
    return f"{registry}/{owner}/{repo}"


def resolve_shorthand(shorthand: str) -> tuple[str, str]:
    """Resolve owner/repo or registry/owner/repo to (url, local_path).

    - "owner/repo" -> uses default registry (github.com)
    - "gitlab/owner/repo" -> uses the named registry

    Returns (url, local_path).
    """
    parts = shorthand.split("/")
    if len(parts) == 2:
        # owner/repo -> default registry (github)
        owner, repo = parts
        registry = "github"
        url = normalize_repo_url(registry, owner, repo)
        return url, f"{registry}/{owner}/{repo}"
    elif len(parts) == 3:
        # registry/owner/repo
        registry, owner, repo = parts
        find_registry(registry)  # raises if unknown
        url = normalize_repo_url(registry, owner, repo)
        return url, f"{registry}/{owner}/{repo}"
    else:
        raise ValueError(f"expected owner/repo or registry/owner/repo, got: {shorthand}")


# ---------------------------------------------------------------------------
# Compat helpers — thin wrappers for callers that use domain directly
# ---------------------------------------------------------------------------


def domain_to_registry(domain: str) -> str:
    """Map a hostname to its registry short name. Raises ValueError if unknown."""
    for r in _all_registries():
        if isinstance(r, DomainRegistry) and r._domain_matches(domain):
            return r.name
    raise ValueError(f"unknown registry host: {domain} (configure in {config_dir() / 'config.yaml'})")


def registry_to_domain(registry: str) -> str:
    """Reverse lookup: short name to domain. Raises ValueError if not a domain registry."""
    r = find_registry(registry)
    if isinstance(r, DomainRegistry):
        return r.domain
    raise ValueError(f"registry '{registry}' is not domain-based")
