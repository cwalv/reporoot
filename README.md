# reporoot

**Monorepo ergonomics without the monorepo.**

Your code already spans multiple repos — your own projects, forks, dependencies, reference implementations. Reporoot gives them a shared workspace so every tool that touches the filesystem — editors, grep, agents, debuggers, build tools — works across all of them. Repos stay sovereign: normal clones, normal branches, normal git.

```
reporoot/
├── github/
│   ├── myorg/
│   │   ├── server/          # your code
│   │   ├── web/             # your code
│   │   └── protocol/        # shared types, used by both
│   └── socketio/
│       └── engine.io/       # your fork with reconnection fixes
├── projects/
│   └── web-app/
│       ├── web-app.repos    # which repos, what roles
│       └── web-app.lock.repos
├── package.json             # generated: npm workspaces
├── go.work                  # generated: Go workspace
└── web-app.code-workspace   # generated: VS Code workspace
```

One `reporoot activate web-app` generates the ecosystem workspace files, and `import { Thing } from '@myorg/protocol'` just works — resolved locally, no `file:../../` paths.

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
reporoot fetch myorg/web-app    # clones project + all its repos
```

**Adopting existing repos:**

```bash
cd ~/reporoot
reporoot activate web-app       # wires existing repos into workspace
```

`reporoot activate` reads the project's `.repos` file and runs integration hooks — generating npm workspaces, `go.work`, uv workspaces, gita config, and a VS Code workspace — so cross-repo imports resolve locally without path hacks.

## Three layers

### 1. The directory tree

Repos live under one root at `{registry}/{owner}/{repo}/`. This is just a directory convention — no tooling required. But every tool benefits: grep finds results across repos, editors navigate the full tree, agents see all the code.

### 2. Ecosystem wiring

`reporoot activate` generates per-ecosystem workspace files from the active project's repos:

| Ecosystem | Generated file | What it enables |
|---|---|---|
| **Node** (npm) | `package.json` with `workspaces` | `import { x } from '@myorg/shared'` resolves locally |
| **Go** | `go.work` | `import "myorg/shared"` resolves locally |
| **Python** (uv) | `pyproject.toml` with `[tool.uv.workspace]` | editable installs across repos |
| **gita** | `.gita/` config | `gita ll`, `gita super pull`, role-based groups |
| **VS Code** | `{project}.code-workspace` | single-root workspace, non-project repos hidden |

Each integration auto-detects relevant repos (has `package.json`? include in npm workspaces) and skips gracefully if the tool isn't installed.

### 3. Reproducibility

A `.repos` file declares which repos belong to a project. `reporoot lock` snapshots every repo's HEAD into a `.lock.repos` file — the multi-repo equivalent of a monorepo commit hash.

```bash
# On a new machine — one command to reproduce the full workspace
reporoot fetch myorg/web-app
```

`sha256sum web-app.lock.repos` gives a single fingerprint for the entire project state.

## Projects

Projects are named views over subsets of repos, with roles that signal how freely code should be changed:

```yaml
# projects/web-app/web-app.repos
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

Repos can appear in multiple projects with different roles. Switching projects is fast — repos are already on disk, only the ecosystem wiring changes:

```bash
reporoot activate mobile-app
# Regenerates package.json, go.work, etc. for mobile-app's repos
```

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

## Docs

- [Conventions](docs/reporoot.md) — full design: directory layout, projects, roles, workflows, adjacent tools
- [Integrations](docs/integrations.md) — how each integration works, generated file formats, configuration

## License

MIT
