# reporoot

Monorepo ergonomics for multi-repo workspaces. Repos stay sovereign — normal clones, normal branches, normal git — while a shared directory tree and ecosystem wiring give you cross-repo search, navigation, and local dependency resolution.

## Install

```bash
pipx install reporoot
```

Or with pip:

```bash
pip install reporoot
```

## Quickstart

```bash
# Set up a new workspace
mkdir ~/reporoot && cd ~/reporoot

# Fetch a project — clones the project repo and all its listed repos
reporoot fetch myorg/web-app

# Or if you already have repos on disk, activate a project
reporoot activate web-app
```

`reporoot activate` reads the project's `.repos` file and wires repos into ecosystem workspace mechanisms — npm workspaces, `go.work`, uv workspaces, gita, VS Code — so cross-repo imports resolve locally.

## Commands

| Command | What it does |
|---|---|
| `reporoot` | Show active project and help |
| `reporoot activate {project}` | Set active project, run integration hooks |
| `reporoot deactivate` | Remove derived files, clear active project |
| `reporoot add {url\|path}` | Clone a repo and register it in the active project |
| `reporoot fetch {source}` | Clone a project and all its repos |
| `reporoot resolve` | Print the workspace root path |
| `reporoot lock` | Snapshot repo versions for the active project |
| `reporoot lock-all` | Snapshot repo versions for all projects |
| `reporoot check` | Run convention enforcement checks |

## How it works

The workspace has three layers:

1. **The directory tree** — repos under one root at `{registry}/{owner}/{repo}/`. Every tool benefits: search, navigation, agents, editors.
2. **Ecosystem wiring** — activation hooks generate workspace files (`package.json`, `go.work`, `pyproject.toml`) so cross-package imports resolve locally.
3. **Reproducibility** — a `.repos` file and its `.lock.repos` pin each repo to an exact SHA, making project state reproducible.

See [docs/reporoot.md](docs/reporoot.md) for the full conventions and [docs/integrations.md](docs/integrations.md) for integration details.

## License

MIT
