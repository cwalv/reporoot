"""End-to-end tests — exercises the full CLI workflow with git repos.

These tests use bare git repos as fake "remotes" so they work without
network access.  A temporary directory is registered as a "local" directory
registry via config, so file:// URLs go through the normal registry flow.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _create_bare_repo(path: Path, files: dict[str, str] | None = None) -> Path:
    """Create a bare git repo at *path* with optional files committed.

    Returns the path to the bare repo (usable as a clone URL via file://).
    """
    # Build a temporary non-bare repo, then clone --bare
    work = path.parent / (path.name + "-work")
    work.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=work, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=work, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work, capture_output=True, check=True)

    for name, content in (files or {"README.md": "hello\n"}).items():
        fp = work / name
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)

    subprocess.run(["git", "add", "."], cwd=work, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=work, capture_output=True, check=True)

    # Clone to bare
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--bare", str(work), str(path)], capture_output=True, check=True)
    return path


@pytest.fixture()
def e2e_env(tmp_path: Path, monkeypatch):
    """Set up bare repos that simulate a local directory registry.

    Creates:
    - A directory registry at remotes/ registered as "local" via config
    - Bare repos at remotes/testowner/lib-a.git, remotes/testowner/lib-b.git
    - A bare "project" repo at remotes/testowner/myproject.git containing
      a reporoot.yaml that references the deps via file:// URLs
    - An empty workspace directory to cd into

    Returns a dict with paths and URLs.
    """
    remotes = tmp_path / "remotes"
    remotes.mkdir()

    # Register remotes/ as a "local" directory registry
    config_dir = tmp_path / "config" / "reporoot"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text(f"registries:\n  local: {remotes}\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Dependency repos — structured as {owner}/{repo}.git
    lib_a_bare = _create_bare_repo(remotes / "testowner" / "lib-a.git")
    lib_b_bare = _create_bare_repo(remotes / "testowner" / "lib-b.git")

    lib_a_url = f"file://{lib_a_bare}"
    lib_b_url = f"file://{lib_b_bare}"

    # Project repo — contains reporoot.yaml referencing the deps
    repos_yaml = (
        "repositories:\n"
        "  local/testowner/lib-a:\n"
        "    type: git\n"
        f"    url: {lib_a_url}\n"
        "    version: main\n"
        "    role: primary\n"
        "  local/testowner/lib-b:\n"
        "    type: git\n"
        f"    url: {lib_b_url}\n"
        "    version: main\n"
        "    role: dependency\n"
    )
    project_bare = _create_bare_repo(
        remotes / "testowner" / "myproject.git",
        files={"reporoot.yaml": repos_yaml},
    )
    project_url = f"file://{project_bare}"

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    return {
        "workspace": workspace,
        "project_url": project_url,
        "remotes": remotes,
    }


class TestFetch:
    def test_fetch_from_empty_dir(self, e2e_env, capsys):
        """Bootstrap on a fresh machine: `reporoot fetch` in an empty dir."""
        from reporoot.cli import main

        os.chdir(e2e_env["workspace"])
        main(["fetch", e2e_env["project_url"]])

        captured = capsys.readouterr()
        assert "cloned" in captured.out or "updated" in captured.out

        ws = e2e_env["workspace"]

        # Project repo cloned
        assert (ws / "projects" / "myproject" / "reporoot.yaml").exists()

        # Dependency repos cloned under the "local" registry path
        assert (ws / "local" / "testowner" / "lib-a" / ".git").is_dir()
        assert (ws / "local" / "testowner" / "lib-b" / ".git").is_dir()

        # Active project set
        active = (ws / ".reporoot-active").read_text().strip()
        assert active == "myproject"

    def test_fetch_existing_project_errors(self, e2e_env, capsys):
        """Double-fetch gives a clear error."""
        from reporoot.cli import main

        os.chdir(e2e_env["workspace"])
        main(["fetch", e2e_env["project_url"]])

        with pytest.raises(SystemExit, match="already exists"):
            main(["fetch", e2e_env["project_url"]])


class TestFullCycle:
    def test_fetch_then_lock_then_check(self, e2e_env, capsys):
        """Full cycle: fetch -> lock -> check passes."""
        from reporoot.cli import main

        os.chdir(e2e_env["workspace"])
        main(["fetch", e2e_env["project_url"]])

        # Lock
        capsys.readouterr()  # clear fetch output
        main(["lock"])

        captured = capsys.readouterr()
        assert "wrote reporoot.lock" in captured.out

        lock_file = e2e_env["workspace"] / "projects" / "myproject" / "reporoot.lock"
        assert lock_file.exists()

        # Check should pass (no issues)
        capsys.readouterr()
        main(["check"])
        captured = capsys.readouterr()
        assert "all checks passed" in captured.out

    def test_fetch_then_activate_idempotent(self, e2e_env, capsys):
        """Re-activating the same project works."""
        from reporoot.cli import main

        os.chdir(e2e_env["workspace"])
        main(["fetch", e2e_env["project_url"]])

        capsys.readouterr()
        main(["activate", "myproject"])
        captured = capsys.readouterr()
        assert "already active" in captured.out


class TestCheckOutput:
    def test_check_summary_vs_verbose(self, e2e_env, capsys):
        """Default check shows counts; -v shows details."""
        from reporoot.cli import main

        ws = e2e_env["workspace"]
        os.chdir(ws)
        main(["fetch", e2e_env["project_url"]])

        # Create an orphan repo under the "local" registry dir
        orphan = ws / "local" / "testowner" / "orphan"
        orphan.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=orphan, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=orphan, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=orphan, capture_output=True, check=True)
        (orphan / "x").write_text("x")
        subprocess.run(["git", "add", "."], cwd=orphan, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=orphan, capture_output=True, check=True)

        # Default (summary)
        capsys.readouterr()
        with pytest.raises(SystemExit):
            main(["check"])
        captured = capsys.readouterr()
        assert "orphan: 1 repo(s)" in captured.out
        assert "local/testowner/orphan" not in captured.out
        assert "use -v for details" in captured.out

        # Verbose
        capsys.readouterr()
        with pytest.raises(SystemExit):
            main(["check", "-v"])
        captured = capsys.readouterr()
        assert "local/testowner/orphan" in captured.out

    def test_check_stale_lock(self, e2e_env, capsys):
        """Check detects stale lock after new commits."""
        from reporoot.cli import main

        ws = e2e_env["workspace"]
        os.chdir(ws)
        main(["fetch", e2e_env["project_url"]])

        # Lock
        main(["lock"])

        # Make a new commit in lib-a
        lib_a = ws / "local" / "testowner" / "lib-a"
        (lib_a / "new_file.txt").write_text("change\n")
        subprocess.run(["git", "add", "."], cwd=lib_a, capture_output=True, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t.com", "-c", "user.name=T", "commit", "-m", "update"],
            cwd=lib_a,
            capture_output=True,
            check=True,
        )

        # Check should detect stale lock
        capsys.readouterr()
        with pytest.raises(SystemExit):
            main(["check", "-v"])
        captured = capsys.readouterr()
        assert "lock:" in captured.out
        assert "lib-a" in captured.out


class TestDeactivate:
    def test_deactivate_clears_active(self, e2e_env, capsys):
        """Deactivate removes the active project pointer."""
        from reporoot.cli import main

        os.chdir(e2e_env["workspace"])
        main(["fetch", e2e_env["project_url"]])

        active_file = e2e_env["workspace"] / ".reporoot-active"
        assert active_file.exists()

        main(["deactivate"])
        assert not active_file.exists()

    def test_resolve_prints_root(self, e2e_env, capsys):
        """reporoot resolve prints the workspace root."""
        from reporoot.cli import main

        os.chdir(e2e_env["workspace"])
        main(["fetch", e2e_env["project_url"]])

        capsys.readouterr()
        main(["resolve"])
        captured = capsys.readouterr()
        assert str(e2e_env["workspace"]) in captured.out
