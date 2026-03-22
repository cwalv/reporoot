---
title: Home
layout: home
nav_order: 1
permalink: /
---

Software lives in multiple repos. Even a monorepo has upstream dependencies, vendored libraries, etc., where the source of truth is elsewhere. The code you work with almost always spans repos you own, repos you depend on (or forked), and maybe even repos you just want around as a reference.

The value of a monorepo is the workspace — all your code in one directory tree, so every tool that touches the filesystem works across all of it. Reporoot gives you the workspace without merging repos. A project `reporoot.yaml` file declares which repos belong together; `reporoot workspace` creates an isolated working copy with git worktrees and ecosystem wiring so cross-repo imports resolve locally. Repos stay sovereign: normal git, normal branches, normal push/pull.

```
reporoot/
├── github/                                    # Bare repos (shared store)
│   ├── myorg/
│   │   ├── server.git/
│   │   ├── web.git/
│   │   └── protocol.git/
│   └── socketio/
│       └── engine.io.git/
│
├── projects/
│   └── web-app/
│       ├── reporoot.yaml                      # which repos, what roles
│       ├── reporoot.lock                      # pinned SHAs
│       └── workspaces/                        # gitignored
│           ├── default/                       # primary workspace
│           │   ├── github/myorg/server/       # worktree
│           │   ├── github/myorg/web/          # worktree
│           │   ├── github/myorg/protocol/     # worktree
│           │   ├── package.json               # generated: npm workspaces
│           │   ├── go.work                    # generated: Go workspace
│           │   └── node_modules/              # isolated
│           └── agent-task-42/                 # parallel workspace
│               ├── github/myorg/server/
│               ├── github/myorg/protocol/
│               └── package.json
│
└── .gitignore
```

Bare repos at `github/owner/repo.git/` hold the shared git object store. Workspaces at `projects/{name}/workspaces/{ws}/` are isolated working copies with their own branches, worktrees, ecosystem files, and tool state. One fetch benefits all workspaces; `cd` switches between them instantly.

## Why not just...

**...use a monorepo?** You'd need everyone to buy in, and you still have external deps, forks, and reference code outside the repo. The coordination problem exists either way.

**...use git submodules?** Submodules take ownership: detached HEAD by default, can't adopt existing clones, the parent controls the relationship. For repos you don't control, this is backwards.

**...clone repos into a flat directory?** Works for one person who set it up. Fails for: reproducing on a new machine, onboarding someone, remembering why a repo was cloned six months later.

Reporoot is the layer in between — structure and reproducibility without giving up repo independence.

## Install

```bash
pipx install reporoot
```

## Quickstart

**Starting fresh:**

```bash
mkdir ~/reporoot && cd ~/reporoot
reporoot fetch myorg/web-app
# Clones project + all its repos as bare clones
# Creates a default workspace with worktrees and ecosystem wiring
```

**Creating additional workspaces:**

```bash
reporoot workspace web-app review-pr-42
# New isolated workspace — own branches, own node_modules, own everything
cd projects/web-app/workspaces/review-pr-42
```

Inside a workspace, ecosystem commands just work — `npm test --workspaces`, `go test ./...`, `uv run pytest`. Git operations work normally in each worktree.

## Three layers

### 1. The directory tree

Bare repos live under one root at `{registry}/{owner}/{repo}.git/`. This is just a directory convention — no tooling required. Workspaces mirror this layout (without the `.git` suffix) so relative paths in generated files work unchanged.

### 2. Ecosystem wiring

Each workspace gets its own generated ecosystem files:

| Ecosystem | Generated file | What it enables |
|---|---|---|
| **Node** (npm) | `package.json` with `workspaces` | `import { x } from '@myorg/shared'` resolves locally |
| **Go** | `go.work` | `import "myorg/shared"` resolves locally |
| **Python** (uv) | `pyproject.toml` with `[tool.uv.workspace]` | editable installs across repos |
| **gita** | `.gita/` config | `gita ll`, `gita super pull`, role-based groups |
| **VS Code** | `{project}.code-workspace` | single-root workspace, non-project repos hidden |

Each integration auto-detects relevant repos (has `package.json`? include in npm workspaces) and skips gracefully if the tool isn't installed.

### 3. Reproducibility

A `reporoot.yaml` file declares which repos belong to a project. `reporoot lock` snapshots every repo's HEAD into a `reporoot.lock` file — the multi-repo equivalent of a monorepo commit hash.

```bash
# On a new machine — one command to reproduce the full workspace
reporoot fetch myorg/web-app
```

`sha256sum reporoot.lock` gives a single fingerprint for the entire project state.

## Projects

Projects are named views over subsets of repos, with roles that signal how freely code should be changed:

```yaml
# projects/web-app/reporoot.yaml
repositories:
  github/myorg/server:
    type: git
    url: https://github.com/myorg/server.git
    version: main
    role: primary              # your code — change freely
  github/myorg/protocol:
    type: git
    url: https://github.com/myorg/protocol.git
    version: main
    role: primary
  github/socketio/engine.io:
    type: git
    url: https://github.com/myorg/engine.io.git
    version: main
    role: fork                 # your fork — changes ideally go upstream
```

Repos can appear in multiple projects with different roles. Each workspace is an isolated instance of a project — own branches, own tool state, own everything. Create as many as you need:

```bash
reporoot workspace web-app           # default workspace
reporoot workspace web-app hotfix    # parallel workspace for a hotfix
reporoot workspace web-app agent-42  # isolated workspace for an agent
```

## Commands

| Command | What it does |
|---|---|
| `reporoot` | Show current context (root, project, workspace, repos) |
| `reporoot workspace {project} [name]` | Create a workspace (default name: `default`) |
| `reporoot workspace {project} [name] --delete` | Delete a workspace |
| `reporoot workspace {project} [name] --sync` | Sync workspace worktrees with manifest |
| `reporoot workspace {project} --list` | List workspaces for a project |
| `reporoot fetch {source}` | Clone a project and all its repos, create default workspace |
| `reporoot add {url\|path}` | Clone a repo and register it in the active project |
| `reporoot remove {path}` | Remove a repo from the active project |
| `reporoot lock` | Snapshot repo versions for the active project |
| `reporoot lock-all` | Snapshot repo versions for all projects |
| `reporoot check` | Run convention enforcement checks |
| `reporoot resolve` | Print the workspace root path |
| `reporoot activate {project}` | (compat) Set active project, run integrations at root level |
| `reporoot deactivate` | (compat) Remove derived files, clear active project |

## Docs

- [Conventions](docs/reporoot.md) — full design: directory layout, projects, roles, workflows, adjacent tools
- [Integrations](docs/integrations.md) — how each integration works, generated file formats, configuration

## License

MIT
