"""Registry configuration — mapping host domains to local directory names.

Reads ~/.config/reporoot/config.yaml (or $XDG_CONFIG_HOME/reporoot/config.yaml).
Well-known hosts have built-in defaults; only custom registries need configuration.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

# Built-in registry mappings: domain -> short name
_BUILTIN_REGISTRIES: dict[str, str] = {
    "github.com": "github",
    "gitlab.com": "gitlab",
    "bitbucket.org": "bitbucket",
}


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


def registries() -> dict[str, str]:
    """Return {domain: short_name} mapping, built-ins merged with user config.

    User config format (in config.yaml):
        registries:
          internal: git.mycompany.com

    User entries are {short_name: domain}, reversed to {domain: short_name} here.
    """
    result = dict(_BUILTIN_REGISTRIES)
    config = load_config()
    user_registries = config.get("registries", {})
    if user_registries:
        for short_name, domain in user_registries.items():
            result[domain] = short_name
    return result


def registry_names() -> set[str]:
    """Return the set of all known registry short names."""
    return set(registries().values())


def domain_to_registry(domain: str) -> str:
    """Map a hostname to its registry short name. Raises ValueError if unknown."""
    regs = registries()
    if domain in regs:
        return regs[domain]
    # Try without www. prefix
    bare = domain.removeprefix("www.")
    if bare in regs:
        return regs[bare]
    raise ValueError(f"unknown registry host: {domain} (configure in {config_dir() / 'config.yaml'})")


def registry_to_domain(registry: str) -> str:
    """Reverse lookup: short name to domain. Raises ValueError if unknown."""
    regs = registries()
    for domain, name in regs.items():
        if name == registry:
            return domain
    raise ValueError(f"unknown registry: {registry}")


def parse_repo_url(url: str) -> tuple[str, str, str]:
    """Extract (registry, owner, repo) from a git URL.

    Handles:
    - https://github.com/owner/repo.git -> ("github", "owner", "repo")
    - git@gitlab.com:owner/repo.git -> ("gitlab", "owner", "repo")
    - https://git.mycompany.com/owner/repo.git -> ("internal", "owner", "repo")
    """
    url = url.rstrip("/")

    # SSH: git@host:owner/repo.git
    ssh_match = re.match(r"git@([^:]+):(.+?)/(.+?)(?:\.git)?$", url)
    if ssh_match:
        domain = ssh_match.group(1)
        registry = domain_to_registry(domain)
        return registry, ssh_match.group(2), ssh_match.group(3)

    # HTTPS: https://host/owner/repo.git
    parsed = urlparse(url)
    if parsed.hostname:
        registry = domain_to_registry(parsed.hostname)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            repo = parts[1].removesuffix(".git")
            return registry, parts[0], repo

    raise ValueError(f"cannot parse registry/owner/repo from URL: {url}")


def normalize_repo_url(registry: str, owner: str, repo: str) -> str:
    """Canonical HTTPS URL: https://{domain}/{owner}/{repo}.git"""
    domain = registry_to_domain(registry)
    return f"https://{domain}/{owner}/{repo}.git"


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
        # Validate registry is known
        registry_to_domain(registry)  # raises if unknown
        url = normalize_repo_url(registry, owner, repo)
        return url, f"{registry}/{owner}/{repo}"
    else:
        raise ValueError(f"expected owner/repo or registry/owner/repo, got: {shorthand}")
