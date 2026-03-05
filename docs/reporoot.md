---
title: Conventions
layout: default
nav_order: 2
---

Software lives in multiple repos. Even a monorepo has upstream dependencies, vendored libraries, etc., where the source of truth is elsewhere. The code you work with almost always spans repos you own, repos you depend on (or forked), and maybe even repos you just just want around as a reference.

The value of a monorepo is the workspace. All your code lives in one directory tree, so every tool that touches the filesystem — editors, grep, agents, debuggers, build tools — works across all of it. Your code can talk to your other code without ceremony. You also get workspace-wide atomic commit, which is useful, but not the main benefit.

Reporoot provides the workspace without merging repos. Repos live under one root in a predictable layout, so filesystem-level tools work across them naturally. A project `reporoot.yaml` file declares which repos belong together; `reporoot activate` wires them into ecosystem workspace mechanisms (npm workspaces, `go.work`, Cargo workspaces) so cross-repo imports resolve locally. Repos stay sovereign — normal clones, normal branches, normal git.

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
├── .reporoot-active                    # Active project pointer (gitignored)
│
├── projects/                     # Project repos (coordination only)
│   ├── reporoot/                 # Reporoot conventions, this doc
│   │   └── docs/
│   │
│   ├── web-app/
│   │   ├── reporoot.yaml         # Source of truth: which repos, what roles
│   │   ├── reporoot.lock         # Pinned SHAs (committed)
│   │   ├── .reporoot-derived/    # Integration artifacts (symlinked to root)
│   │   │   └── web-app.code-workspace
│   │   └── docs/
│   │
│   └── mobile-app/
│       ├── reporoot.yaml
│       ├── reporoot.lock
│       ├── .reporoot-derived/
│       │   └── mobile-app.code-workspace
│       └── docs/
│
├── github/                       # Normal repos (code only)
│   ├── chatly/
│   │   ├── server/               # in both projects
│   │   ├── web/
│   │   ├── mobile/
│   │   └── protocol/             # in both projects
│   │
│   ├── socketio/
│   │   └── engine.io/            # web-app only (fork)
│   │
│   └── nickel-io/
│       └── push-sdk/             # mobile-app only (dependency)
│
├── package.json                  # Derived: npm workspaces (active project's Node repos)
└── .gitignore
```

- **Normal repos live in one place** (`{registry}/{owner}/{repo}/`), regardless of how many projects reference them.
- **Projects are directories** with a `reporoot.yaml` file, a `reporoot.lock` file, and `docs/`. They don't contain code — build tools are unaware of them.
- **Overlap is natural** — `server` and `protocol` appear in both projects' `reporoot.yaml` files, but there's one clone on disk.
- **Root ecosystem files are derived** — `package.json`, `go.work`, etc. are generated by activation hooks from the active project's repos. Some (like `.code-workspace`) are generated into the project's `.reporoot-derived/` directory and symlinked to the root, allowing them to be committed and customized. Others are written directly to the root and not committed.
- **Repos without an active project stay on disk** — clone something for a quick look; it's an inert directory until you add it to a project.

## The active project

One project is active at a time. The active project's `reporoot.yaml` file drives activation hooks — which repos are wired into `package.json` workspaces, `go.work`, gita config, etc.

```bash
reporoot activate web-app
```

This does three things:

1. **Cleans** — removes symlinks pointing into `projects/` from the previous activation.
2. **Sets the pointer** — writes `web-app` to `.reporoot-active` at the reporoot.
3. **Runs integrations** — each integration's activation hook receives the resolved repo list and generates config files, runs install commands, or performs other setup. See [Integrations](#integrations).

**Important:** Generated files are not kept in sync automatically. If you edit a project's `reporoot.yaml` (add, remove, or change repos), you must re-run `reporoot activate` to regenerate workspace files and re-run install commands. Without re-activation, ecosystem tools see stale config — `package.json` lists the wrong workspaces, `go.work` points to removed modules, `uv sync` installed packages for repos no longer in the project. `reporoot add` handles this for the add-a-repo case (it re-runs activation hooks after updating `reporoot.yaml`), but manual edits require an explicit `reporoot activate`.

### Switching projects

Switching is fast because repos are already on disk. Only the ecosystem wiring changes:

```bash
reporoot activate mobile-app
# Regenerates package.json (drops engine.io, adds push-sdk)
# Runs npm install (relinking, seconds)
```

Repos from the previous project stay on disk. `github/socketio/engine.io/` is still there after switching to mobile-app — it's just not in `package.json` workspaces anymore. It remains accessible for reading, and `reporoot check` knows it belongs to web-app (not an orphan).

### No active project

Deactivating removes integration-generated files and clears the pointer:

```bash
reporoot deactivate
```

After deactivating, anything at the reporoot level that isn't under a registry path or `projects/` is derived state — safe to delete. `reporoot deactivate --hard` removes it all (with interactive confirmation per item, or `--force` to skip prompts).

### Where the pointer lives

`.reporoot-active` is a one-line file at the reporoot, gitignored. It's ephemeral, per-developer state — scoped to the single purpose of "which project is wired up right now."

```
web-app
```

`reporoot` validates the pointer on read: if `.reporoot-active` names a project that doesn't exist in `projects/`, it warns and falls back to no active project.

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
├── .reporoot-derived/    # Integration artifacts (symlinked to root)
│   └── web-app.code-workspace
└── docs/                 # Cross-repo architecture docs, roadmap, coordination
```

### What projects do

Projects answer the question: "I'm working on the web app — which repos matter?"

Without projects, you have a flat list of 20 repos and need tribal knowledge to know which ones are relevant. With an active project, every `reporoot` command — `reporoot lock`, `reporoot check` — and every activation hook is scoped to the repos that matter for that work.

Projects also provide a home for documentation that doesn't belong to any single repo. An architecture decision that spans `server` and `protocol` shouldn't live in either repo — it lives in `projects/web-app/docs/`.

### Fetching a project

On a new machine, you don't clone repos one by one:

```bash
mkdir ~/reporoot && cd ~/reporoot
reporoot fetch chatly/web-app
```

`reporoot fetch` clones the project repo to `projects/web-app/`, reads its `reporoot.yaml`, clones every listed normal repo to its `github/{owner}/{repo}/` path, and activates the project. One command, and you have the complete working environment.

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

There's one clone of `server` on disk. The role annotations may differ between projects — `server` could be `primary` in one and `dependency` in another. The active project's `reporoot.yaml` determines which role applies.

### Project variants via branches

Need a variant of a project — same repos but with an extra dependency, or a different role for one repo? Use a branch in the project repo rather than a separate project:

```bash
cd projects/web-app
git checkout -b experiment
# edit reporoot.yaml (add a repo, change a role)
reporoot activate web-app   # picks up the branch's reporoot.yaml
```

This avoids inventing inheritance or "derived project" machinery. A branch is already a variant with full version history, and `reporoot activate` reads whatever `reporoot.yaml` is checked out.

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

Switching projects means changing which repos are wired into the build:

```bash
reporoot activate mobile-app
```

This runs activation hooks with mobile-app's repo list — regenerating ecosystem workspace files (`package.json`, `go.work`), gita config, etc. Repos from the previous project stay on disk — they're just not wired into the build.

Friction arises when two projects need the same repo in *different states*:
- **Different branches** — can't have `server` on `feature-A` and `main` simultaneously without worktrees.
- **Different versions** — web-app pins `engine.io` at a tagged release; mobile-app wants `main`. Switching requires a checkout.

Usually both projects want `main` and the switch is instant.

### Adding and removing repos

With `reporoot`:

```bash
reporoot add https://github.com/example/some-lib.git --role dependency
# Clones to github/example/some-lib/
# Adds to active project's reporoot.yaml
# Re-runs activation hooks
```

```bash
reporoot remove github/example/some-lib
# Removes from active project's reporoot.yaml
# Re-runs activation hooks

reporoot remove github/example/some-lib --delete
# Also rm -rf the clone from disk (with confirmation)
```

Manually:

```bash
# Clone into the provenance path
git clone https://github.com/example/some-lib.git github/example/some-lib

# Add to the project reporoot.yaml (edit YAML by hand)
# Re-run activation hooks
reporoot activate web-app
```

Removing manually: delete the entry from `reporoot.yaml`, optionally `rm -rf` the directory, update lock file. `reporoot check` will flag repos on disk that aren't in any project.

## `reporoot`

A standalone Python CLI that manages repos following reporoot conventions using direct git commands. Installed out of band — not part of any project. Nothing about the underlying `reporoot.yaml` files changes; `reporoot` is a convenience layer on top.

### Commands

| Command | What it does |
|---|---|
| `reporoot` | Show active project and help. |
| `reporoot activate {project}` | Set active project, run integration hooks (npm, go, uv, gita, vscode). |
| `reporoot deactivate` | Remove integration-generated files, clear active project. |
| `reporoot deactivate --hard` | Also remove tool state (node_modules, .venv, etc.) with interactive confirmation. Add `--force` to skip prompts. |
| `reporoot add {url\|path}` | Clone a repo and register it in the active project's `reporoot.yaml`. URL → derive local path from registry config. With `--role`, sets the role annotation. |
| `reporoot remove {path}` | Remove a repo from the active project's `reporoot.yaml` and re-run activation hooks. With `--delete`, also removes the clone from disk (confirms unless `--force`). |
| `reporoot fetch {source}` | Clone a project repo and all its listed repos. Source: URL, `registry/owner/project`, or `owner/project` (defaults to github). |
| `reporoot resolve` | Print the workspace root path. Useful for scripting: `cd $(reporoot resolve)`. |
| `reporoot lock` | Snapshot repo versions into the active project's lock file. |
| `reporoot lock-all` | Snapshot repo versions for all projects. Updates shared repos across projects. |
| `reporoot check` | Convention enforcement. Scans all project `reporoot.yaml` files to detect orphaned clones, dangling references, missing role annotations, stale locks, and integration issues. |

### `reporoot check` and multi-project awareness

`reporoot check` is the one command that looks beyond the active project. It scans all `projects/*/reporoot.yaml` files to build a complete inventory of known repos. This prevents false orphan warnings — a repo from an inactive project is not an orphan.

| Check | Description |
|---|---|
| **Orphaned clones** | Directories under registry paths not listed in ANY project `reporoot.yaml` |
| **Dangling references** | Entries in a `reporoot.yaml` pointing to paths not on disk |
| **Missing role** | `reporoot.yaml` entries without a `role` field |
| **Stale lock** | Active project's `reporoot.lock` doesn't match current repo SHAs |
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

Integrations are pluggable units that each derive config for one tool from the repo list. Each participates in activation hooks (`reporoot activate` — generate files, run install commands) and check hooks (`reporoot check` — read-only inspection). Integration config lives in the project's `reporoot.yaml` under an `integrations` key; only overrides need to be listed.

| Integration | Default enabled | Auto-detects | Generates |
|---|---|---|---|
| `npm-workspaces` | yes | repos with `package.json` | root `package.json` + `npm install` |
| `go-work` | yes | repos with `go.mod` | `go.work` |
| `uv-workspace` | yes | repos with `pyproject.toml` | root `pyproject.toml` + `uv sync` |
| `gita` | yes | all repos | `.gita/` config directory |
| `vscode-workspace` | yes | all repos | `{project}.code-workspace` + `files.exclude` |

### Generated artifacts and symlinks

Some integrations generate files that need to exist at the workspace root (like `.code-workspace`). Rather than writing these directly to the root, integrations generate them into `.reporoot-derived/` inside the project directory and symlink them to the root. This has three benefits:

1. **Committable** — the derived file lives in the project repo, so customizations can be committed and shared. For example, adding VS Code settings or extension recommendations to the workspace file.
2. **Graceful merging** — on activation, integrations only update the keys they manage (e.g., `folders` and `settings.files.exclude` in `.code-workspace`), preserving user-added keys (e.g., other settings, `extensions`). Adding or removing repos updates the configuration without losing manual customizations.
3. **Project-named** — the workspace file is named after the project (e.g., `web-app.code-workspace`), making the active project visible in the VS Code title bar. Switching projects removes the old symlink and creates a new one.

The `.reporoot-derived/` directory is created automatically by integrations that need it. Files in this directory are managed by `reporoot activate` — the integration-controlled portions are regenerated, while user-customized portions are preserved.

The vscode-workspace integration uses a single-root workspace (the reporoot directory) and generates `files.exclude` entries to hide repos and project directories not in the active project. This keeps search and glob behavior simple — no multi-root workspace complications — while still showing only what's relevant.

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
