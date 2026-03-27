---
title: Conventions
layout: default
nav_order: 2
---

Software lives in multiple repos. Even a monorepo has upstream dependencies, vendored libraries, etc., where the source of truth is elsewhere. The code you work with almost always spans repos you own, repos you depend on (or forked), and maybe even repos you just just want around as a reference.

The value of a monorepo is the workspace. All your code lives in one directory tree, so every tool that touches the filesystem — editors, grep, agents, debuggers, build tools — works across all of it. Your code can talk to your other code without ceremony. You also get workspace-wide atomic commit, which is useful, but not the main benefit.

Reporoot provides the workspace without merging repos. A project `reporoot.yaml` file declares which repos belong together; `reporoot workspace` creates an isolated working copy with git worktrees and ecosystem wiring (npm workspaces, `go.work`, Cargo workspaces) so cross-repo imports resolve locally. Repos stay sovereign — normal git, normal branches, normal push/pull.

## Core idea

The workspace has three layers:

1. **The directory tree** — repos under one root. Every tool benefits: search, navigation, agents, editors. This is the convention alone — no tooling required.
2. **Ecosystem wiring** — activation hooks generate workspace files (`package.json`, `go.work`) so cross-package imports resolve locally. `import { thing } from '@myorg/shared'` just works.
3. **Reproducibility** — a committed `reporoot.yaml` file and its `reporoot.lock` pin each repo to an exact SHA, making the project state reproducible from a single project repo.

The only difference from a monorepo commit: updating the lock file is two steps instead of one. You commit in individual repos first, then regenerate and commit the lock file. This is two-phase commit — the lock update is detectable and reversible:

```bash
# 1. Commit in individual repos (already done)
# 2. Update and commit the lock file
reporoot lock
cd projects/web-app
git add reporoot.lock && git commit -m "lock: add payment endpoint"
```

To reproduce a project from scratch:

```bash
pip install reporoot
mkdir reporoot && cd reporoot
reporoot fetch chatly/web-app
```

`sha256sum reporoot.lock` gives a single fingerprint for the project state — the multi-repo equivalent of `git rev-parse HEAD`.

### Why not git submodules?

Git submodules aim to solve a similar problem — coordinating code across repos — but take a different approach. The feature mapping is close:

| Reporoot | Git submodules |
|---|---|
| project `reporoot.yaml` | `.gitmodules` |
| project `reporoot.lock` | SHA stored in parent tree (inherent) |
| `reporoot fetch` | `git submodule update --init --recursive` |
| `reporoot lock` | `git add <submodule>` (records current SHA) |
| `gita super` / `gita shell` | `git submodule foreach` |

Submodules are better at one thing: **atomic locking**. The SHA is part of the parent's git tree — there's no two-phase commit. When you commit the parent, the lock updates atomically. Reporoot's explicit lock file is the price of not using submodules.

But submodules take ownership in ways that conflict with multi-repo development:

- **Detached HEAD** — submodules check out a SHA, not a branch. You `cd` into one and you're in detached HEAD. You have to `git checkout main` before working. Every repo, every time.
- **Can't adopt existing clones** — submodules want to own the clone. You can't take 16 repos already on disk and retroactively make them submodules.
- **Parent owns the relationship** — updating a submodule means: commit in child, `cd` to parent, `git add child`, commit parent. The parent is always in the loop. For reference repos you don't control, this is backwards.
- **No partial fetch** — submodules are all-or-nothing per parent. No "fetch only the web-app project's repos." No project-scoped views.
- **No roles** — submodules are a flat list. No way to distinguish primary from reference, no per-project role assignments.
- **Flat nesting only** — if a dependency uses submodules, you get recursive submodule hell. Reporoot's flat `{registry}/{owner}/{repo}` layout avoids nesting.

The design trade-off: submodules get atomic locking for free by taking ownership. Reporoot gives up atomic locking to preserve sovereignty — repos stay on normal branches, you work in them normally, and the lock file is an explicit (two-step) operation.

## Two kinds of repos

The reporoot contains two fundamentally different kinds of repos, distinguished by path:

| Kind | Path | Purpose |
|------|------|---------|
| **Normal** | `{registry}/{owner}/{repo}/` | Code. Build tools look here. Other repos import from here. Listed in root `package.json` workspaces, `go.work`, etc. |
| **Project** | `projects/{name}/` | Coordination. `reporoot.yaml`, lock files, docs. Build tools never see these. No importable code. |

Path encodes kind — you can tell what a repo is for from its location. Build tools (npm/pnpm, Go, Nx) are configured to look inside registry directories (`github/`, `gitlab/`, etc.), not `projects/`. Project repos have GitHub URLs (for fetchability) but their local path reflects their *role*, not their provenance.

Project paths default to `projects/{name}/` for ergonomics. If names collide (two owners with a project called `web-app`), `reporoot fetch` errors and suggests a scoped path: `projects/{owner}/{name}/` or `projects/{registry}/{owner}/{name}/`. `reporoot activate` requires the path as created — if the project lives at `projects/chatly/web-app/`, you must use `reporoot activate chatly/web-app`, not just `web-app`. Errors if no matching directory with a `reporoot.yaml` file exists.

## Directory layout

Normal repos are organized by provenance: `{registry}/{owner}/{repo}/`. The first path segment is a **registry** — a short name for where the repo lives. `reporoot` ships with built-in defaults for well-known hosts (`github.com` → `github`, `gitlab.com` → `gitlab`, `bitbucket.org` → `bitbucket`); custom registries are configured in `reporoot`'s own config. A registry can be domain-based (e.g., `git.mycompany.com` → `internal`, handles `https://` and `git@` URLs) or directory-based (e.g., `/srv/repos` → `local`, handles `file://` URLs). This follows Go's GOPATH precedent (`$GOPATH/src/github.com/owner/repo`), shortened for ergonomics.

Projects are named views over subsets of repos, with their own docs and lock files.

Example — a team building a chat product with a web app and mobile app:

```
reporoot/
├── github/                       # Bare repos (shared git object store)
│   ├── chatly/
│   │   ├── server.git/           # in both projects
│   │   ├── web.git/
│   │   ├── mobile.git/
│   │   └── protocol.git/         # in both projects
│   │
│   ├── socketio/
│   │   └── engine.io.git/        # web-app only (fork)
│   │
│   └── nickel-io/
│       └── push-sdk.git/         # mobile-app only (dependency)
│
├── projects/
│   ├── web-app/
│   │   ├── reporoot.yaml         # Source of truth: which repos, what roles
│   │   ├── reporoot.lock         # Pinned SHAs (committed)
│   │   ├── docs/
│   │   └── workspaces/           # gitignored
│   │       ├── default/          # primary workspace
│   │       │   ├── github/chatly/server/    # worktree
│   │       │   ├── github/chatly/web/       # worktree
│   │       │   ├── github/chatly/protocol/  # worktree
│   │       │   ├── package.json             # generated: npm workspaces
│   │       │   └── node_modules/            # isolated
│   │       └── review-pr-42/     # parallel workspace
│   │           └── ...
│   │
│   └── mobile-app/
│       ├── reporoot.yaml
│       ├── reporoot.lock
│       └── workspaces/
│           └── default/
│               └── ...
│
└── .gitignore
```

- **Bare repos are shared** — `github/owner/repo.git/` holds the git object store. All workspaces draw from the same bare repos.
- **Workspaces are isolated** — each workspace has its own worktrees, ecosystem files, and tool state. One fetch benefits all workspaces; `cd` switches between them instantly.
- **Projects are directories** with a `reporoot.yaml` file, a `reporoot.lock` file, and `docs/`. They don't contain code — build tools are unaware of them.
- **Overlap is natural** — `server` and `protocol` appear in both projects' `reporoot.yaml` files, but there's one bare repo on disk.
- **Repos without a project stay on disk** — clone something for a quick look; it's an inert directory until you add it to a project.

## Workspaces

A workspace is an isolated working copy of a project — its own git worktrees, ecosystem files, and tool state. Create as many as you need:

```bash
reporoot workspace web-app           # default workspace
reporoot workspace web-app hotfix    # parallel workspace for a hotfix
reporoot workspace web-app agent-42  # isolated workspace for an agent
```

Each workspace:

1. **Creates worktrees** from bare repos for every repo in `reporoot.yaml`, on a per-workspace branch (`{ws}/{version}` tracking `origin/{version}`).
2. **Runs integrations** — generates ecosystem files (`package.json`, `go.work`, etc.) and runs install commands inside the workspace directory.

Workspaces are fully isolated. `node_modules/`, `.venv/`, branches, and generated files are per-workspace. One workspace can be on `feature-A` while another is on `main`.

### Workspace context

Commands like `add`, `remove`, `lock`, and `check` infer the project and workspace from your CWD:

- **In a workspace dir** — uses that workspace directly.
- **In a project dir** — resolves to the project's configured `default_workspace` (defaults to `"default"`).
- **Override** — use `--project` and `--workspace` flags.

### Syncing after manifest changes

If you edit `reporoot.yaml` (add/remove repos), sync the workspace:

```bash
reporoot workspace web-app --sync
```

`reporoot add` and `reporoot remove` handle this automatically — they update `reporoot.yaml` and re-run integration hooks in one step.

## Repos files

YAML format with a `repositories` root key. Each entry is keyed by local path and has `type`, `url`, `version`, and `role` fields. Based on vcstool's `.repos` format, extended with `role` and an optional `integrations` key for integration configuration (see [Integrations](#integrations)). Each project directory contains a `reporoot.yaml` (the declaration) and optionally a `reporoot.lock` (pinned SHAs).

### Project `reporoot.yaml` files

The source of truth for which repos belong to a project. Committed in the project repo, with version history:

```yaml
# projects/web-app/reporoot.yaml
repositories:
  github/chatly/server:
    type: git
    url: https://github.com/chatly/server.git
    version: main
    role: primary
  github/chatly/web:
    type: git
    url: https://github.com/chatly/web.git
    version: main
    role: primary
  github/chatly/protocol:
    type: git
    url: https://github.com/chatly/protocol.git
    version: main
    role: primary                # shared message types
  github/socketio/engine.io:
    type: git
    url: https://github.com/chatly/engine.io.git
    version: main
    role: fork                   # added reconnection logic
```

### Lock files

Generated by `reporoot lock`, same format but with resolved SHAs instead of branch names:

```yaml
# projects/web-app/reporoot.lock — generated, committed
repositories:
  github/chatly/server:
    type: git
    url: https://github.com/chatly/server.git
    version: 7a3b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b
  github/chatly/web:
    type: git
    url: https://github.com/chatly/web.git
    version: e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0
  # ...
```

Lock files live alongside `reporoot.yaml` in the project directory, committed in the project repo. Each project owns its own lock state.

`sha256sum reporoot.lock` is the project fingerprint. Two developers with the same lock file checksum have identical source for every repo in the project.

## Projects

A project is a directory under `projects/` with a `reporoot.yaml` file, a lock file, and a `docs/` directory. (We use "project" to avoid overloading "workspace," which each ecosystem already uses for its own build wiring — npm workspaces, `go.work`, Cargo workspaces. A project is also more than build wiring — it includes docs, roles, and lock files.)

```
projects/web-app/
├── reporoot.yaml         # Which repos, with what roles
├── reporoot.lock         # Pinned SHAs (reporoot lock)
├── docs/                 # Cross-repo architecture docs, roadmap, coordination
└── workspaces/           # gitignored — isolated working copies
    └── default/
        ├── github/chatly/server/    # worktree
        ├── package.json             # generated
        └── web-app.code-workspace   # generated
```

### What projects do

Projects answer the question: "I'm working on the web app — which repos matter?"

Without projects, you have a flat list of 20 repos and need tribal knowledge to know which ones are relevant. With a project, every `reporoot` command — `reporoot lock`, `reporoot check` — and every workspace is scoped to the repos that matter for that work.

Projects also provide a home for documentation that doesn't belong to any single repo. An architecture decision that spans `server` and `protocol` shouldn't live in either repo — it lives in `projects/web-app/docs/`.

### Fetching a project

On a new machine, you don't clone repos one by one:

```bash
mkdir ~/reporoot && cd ~/reporoot
reporoot fetch chatly/web-app
```

`reporoot fetch` clones the project repo to `projects/web-app/`, reads its `reporoot.yaml`, creates bare clones for every listed repo, and sets up a default workspace with worktrees and ecosystem wiring. One command, and you have the complete working environment.

### Overlap between projects

Same repo, different projects — natural and expected:

```
projects/web-app/reporoot.yaml:
  github/chatly/server           role: primary
  github/chatly/protocol         role: primary

projects/mobile-app/reporoot.yaml:
  github/chatly/server           role: primary
  github/chatly/protocol         role: primary
```

There's one bare repo of `server` on disk. The role annotations may differ between projects — `server` could be `primary` in one and `dependency` in another. Each project's `reporoot.yaml` determines which role applies.

### Project variants via branches

Need a variant of a project — same repos but with an extra dependency, or a different role for one repo? Use a branch in the project repo rather than a separate project:

```bash
cd projects/web-app
git checkout -b experiment
# edit reporoot.yaml (add a repo, change a role)
reporoot workspace web-app experiment   # new workspace reads the branch's reporoot.yaml
```

This avoids inventing inheritance or "derived project" machinery. A branch is already a variant with full version history.

## Roles

Roles signal **change resistance** — how freely you (or an agent) should modify the code:

| Role | Change resistance | Meaning |
|------|-------------------|---------|
| `primary` | None | Your code. Change it if it's an improvement. |
| `fork` | Low | Forked upstream. Ideally changes accepted upstream, but expediency is fine. |
| `dependency` | Medium | Code you build against. Changes need upstream acceptance, or convert to a fork. |
| `reference` | High | Cloned for reading/study during design. No local changes. Could be removed when done. |

**Roles are per-project, not per-repo.** The same repo can have different roles in different projects. `engine.io` is a `fork` in web-app (patched for reconnection) but could be a `dependency` in another project (using it unmodified). The active project's `reporoot.yaml` determines the current role.

Roles are a first-class field in `reporoot.yaml`:

```yaml
  github/socketio/engine.io:
    type: git
    url: https://github.com/chatly/engine.io.git
    version: main
    role: fork                   # added reconnection logic
```

**Directory owner as heuristic** — `github/chatly/` is likely primary, `github/{other}/` is likely reference or dependency. But this is a default, not a rule — projects override it.

## Workflows

### Branching across repos

A feature spanning `server` and `protocol`: create a branch with the same name in both repos. gita makes this a single command across all primary repos:

```bash
gita super primary checkout -b feature/threads
```

Paths are stable regardless of branch — `github/chatly/server` always resolves to the same directory. Only the checked-out content changes.

Working on two features simultaneously in the same repo requires `git worktree`, sequential switching, or a second clone — but this is the same constraint as a monorepo. Multi-repo just makes it per-repo rather than all-or-nothing.

### Switching projects

Each project has its own workspaces. Switch by `cd`-ing into the workspace you want to work in:

```bash
cd projects/mobile-app/workspaces/default
```

Since workspaces are fully isolated (own worktrees, own `node_modules/`, own branches), there's no conflict between projects — you can have `web-app/default` and `mobile-app/default` active simultaneously.

### Adding and removing repos

With `reporoot`:

```bash
reporoot add https://github.com/example/some-lib.git --role dependency
# Creates bare clone at github/example/some-lib.git/
# Adds worktree to the current workspace
# Adds to project's reporoot.yaml
# Re-runs integration hooks
```

```bash
reporoot remove github/example/some-lib
# Removes worktree from the current workspace
# Removes from project's reporoot.yaml
# Re-runs integration hooks

reporoot remove github/example/some-lib --delete
# Also removes the bare repo from disk (with confirmation)
```

Removing manually: delete the entry from `reporoot.yaml`, run `reporoot workspace <project> --sync` to reconcile worktrees. `reporoot check` will flag repos on disk that aren't in any project.

## `reporoot`

A standalone Python CLI that manages repos following reporoot conventions using direct git commands. Installed out of band — not part of any project. Nothing about the underlying `reporoot.yaml` files changes; `reporoot` is a convenience layer on top.

### Commands

| Command | What it does |
|---|---|
| `reporoot` | Show current context (root, project, workspace, repos). |
| `reporoot workspace {project} [name]` | Create a workspace (default name from `reporoot.yaml` or `"default"`). |
| `reporoot workspace {project} --delete` | Delete a workspace. |
| `reporoot workspace {project} --sync` | Sync workspace worktrees with manifest. |
| `reporoot workspace {project} --list` | List workspaces for a project. |
| `reporoot fetch {source}` | Clone a project repo and all its listed repos, create default workspace. |
| `reporoot add {url\|path}` | Bare-clone a repo, add worktree to the current workspace, register in `reporoot.yaml`. With `--role`, sets the role annotation. |
| `reporoot remove {path}` | Remove worktree, remove from `reporoot.yaml`, re-run integration hooks. With `--delete`, also removes the bare repo (confirms unless `--force`). |
| `reporoot lock` | Snapshot repo versions from the current workspace into the project's lock file. |
| `reporoot lock-all` | Snapshot repo versions for all projects. |
| `reporoot check` | Convention enforcement: orphaned clones, dangling references, missing roles, stale locks, workspace drift, integration checks. |
| `reporoot resolve` | Print the workspace root (if in a workspace) or reporoot root. Useful for scripting: `cd $(reporoot resolve)`. |

### `reporoot check` and multi-project awareness

`reporoot check` scans all `projects/*/reporoot.yaml` files to build a complete inventory of known repos. This prevents false orphan warnings — a repo from another project is not an orphan.

| Check | Description |
|---|---|
| **Orphaned clones** | Directories under registry paths not listed in ANY project `reporoot.yaml` |
| **Orphaned bare repos** | Bare repos (`.git` dirs) not listed in any project |
| **Dangling references** | Entries in a `reporoot.yaml` pointing to paths not on disk |
| **Missing role** | `reporoot.yaml` entries without a `role` field |
| **Stale lock** | Project's `reporoot.lock` doesn't match current workspace HEAD SHAs |
| **Workspace drift** | Worktrees missing from workspace or extra worktrees not in manifest |
| **Integration checks** | Each integration's check hook reports tool availability, stale config, etc. (see [Integrations](#integrations)) |

### `reporoot lock-all`

`reporoot lock-all` updates lock files for every project repo on disk, not just the active one. If you've been working in the web-app context and made commits to `server` and `protocol`, `reporoot lock-all` also updates the `reporoot.lock` in mobile-app's project directory (since both projects reference those repos).

This gives you the monorepo property of "one action captures all state" — distributed across project repos. Each project repo can then be committed independently, and each remains independently bootstrappable via `reporoot fetch`.

### Bootstrap on a new machine

```bash
pip install reporoot
mkdir ~/reporoot && cd ~/reporoot
reporoot fetch chatly/web-app
```

## Integrations

Integrations are pluggable units that each derive config for one tool from the repo list. Each participates in activation hooks (run when creating/syncing workspaces) and check hooks (`reporoot check` — read-only inspection). Integration config lives in the project's `reporoot.yaml` under an `integrations` key; only overrides need to be listed.

| Integration | Default enabled | Auto-detects | Generates |
|---|---|---|---|
| `npm-workspaces` | yes | repos with `package.json` | `package.json` + `npm install` |
| `go-work` | yes | repos with `go.mod` | `go.work` |
| `uv-workspace` | yes | repos with `pyproject.toml` | `pyproject.toml` + `uv sync` |
| `gita` | yes | all repos | `gita/` config directory |
| `vscode-workspace` | yes | all repos | `{project}.code-workspace` |

All generated files live inside the workspace directory. Integrations merge into existing files where possible — for example, the vscode-workspace integration preserves user-added settings and extensions while updating managed keys (`folders`, `settings.git.*`).

See [integrations.md](integrations.md) for generated file formats, configuration, and details on each integration.

## Adjacent tools

Reporoot solves "which repos, at what versions, in what structure." Several adjacent tools solve other layers — toolchain versions, environment activation, containerized dev environments, CI checkout. They're complementary, and the active project's state makes many of them easier to configure.

### What's derivable from project state

A project's `reporoot.yaml` + the files generated by activation hooks already imply most of the dev environment:

| Layer | Derivable? | How |
|---|---|---|
| **Repos on disk** | Yes | `reporoot fetch` — the whole point |
| **Toolchains needed** | Yes | `package.json` exists → Node, `go.work` exists → Go |
| **Toolchain versions** | Partially | Ecosystem files often pin versions (`.nvmrc`, `go.mod`'s go directive). `.mise.toml` at root fills the gap. |
| **Workspace deps** | Yes | `npm install`, `go work sync` — deterministic once repos + workspace files exist |
| **Editor workspace** | Yes | `.code-workspace` folders directly derivable from project `reporoot.yaml` |
| **Base image / OS packages** | No | System-level, not inferrable from repo structure |
| **Services** | No | Databases, message queues — runtime deps, not repo deps |
| **Secrets / env vars** | No | Out of scope |

### Build orchestration (Nx, Turborepo, etc.)

Build orchestration tools add dependency-aware task ordering, caching, and affected analysis on top of the workspace files that activation hooks generate. See the [Build orchestration](integrations.md#build-orchestration) section of integrations.md.

### mise / asdf — toolchain versions

[mise](https://mise.jdx.dev/) (formerly rtx) manages language runtime versions with a single `.mise.toml` at the reporoot:

```toml
# .mise.toml at reporoot/
[tools]
node = "22"
go = "1.22"
```

### direnv — environment activation

[direnv](https://direnv.net/) auto-activates environments when you `cd` into a directory:

```bash
# .envrc at reporoot/
use mise                                      # activate toolchain versions
export GITA_PROJECT_HOME="$PWD/.gita"         # point gita at reporoot-derived config
```

### Devcontainers / Codespaces

`reporoot fetch` replaces a wall of `git clone` commands in `postCreateCommand`:

```jsonc
// .devcontainer/devcontainer.json
{
  "features": {
    "ghcr.io/devcontainers/features/node:1": {},
    "ghcr.io/devcontainers/features/go:1": {}
  },
  "postCreateCommand": "pip install reporoot && reporoot fetch chatly/web-app",
  "forwardPorts": [5432]
}
```

### Nix flakes — structural parallel

[Nix flakes](https://wiki.nixos.org/wiki/Flakes) are the deepest structural parallel. `flake.nix` inputs = project `reporoot.yaml`, `flake.lock` = project `reporoot.lock`, `devShell` = toolchain+deps setup. The difference: Nix owns the entire build graph and is all-or-nothing. Reporoot is deliberately lighter — just repos and conventions, composable with whatever build/env tools you prefer.

### CI multi-repo checkout

`reporoot.yaml` can drive a reusable checkout action — same pattern as `reporoot fetch` but in CI:

```yaml
# .github/workflows/ci.yml
- uses: actions/checkout@v4        # this repo (projects/web-app)
- run: pip install reporoot && reporoot fetch  # reads reporoot.yaml, clones code repos
- run: npm install && npm test
```
