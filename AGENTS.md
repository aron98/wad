# AGENTS.md — WAD (Worktree Agent Devcontainers)

This repository provides **`wad`**, a small Bash CLI that:

- creates **git worktrees** for parallel development (`.worktrees/<env>`)
- generates a per-worktree **docker compose** file from a template
- starts an isolated **devcontainer** per worktree (one Docker network per env)
- optionally starts/attaches a **goose** coding agent in a **tmux** session inside the devcontainer

The repo is intentionally minimal: the product is the `wad` script plus documentation.

---

## Quick orientation

### What to read first

- `README.md` — user-facing overview and example workflows
- `wad` — the implementation (Bash script). This is the “core codebase”.
- `install.sh` — installer that copies `wad` into `~/.local/bin`

### Key concepts / vocabulary

- **Repo root**: discovered via `git rev-parse --show-toplevel`
- **WAD directory**: `.wad/` (created in *the target project repo* by `wad init`)
- **Worktrees directory**: `.worktrees/<env>/` (created in the target project repo)
- **Environment**: a named worktree + a docker compose project + a dedicated Docker network `wad-<env>`
- **Devcontainer**: the `devcontainer` service in the generated compose file
- **Agent session**: a tmux session inside the devcontainer (default `wad-agent`)

---

## Installation (for humans and CI shells)

Requirements on the host:

- `git`
- `docker` + `docker compose`
- `curl`

Install:

```bash
./install.sh
# installs to ~/.local/bin/wad (or $WAD_INSTALL_DIR)
```

No build step exists; this is a Bash script project.

---

## How WAD is structured

### Repository contents

- `wad`
  Main CLI implementation (Bash). Handles:
  - `init` — creates `.wad/` templates/config in the current repo
  - `new` — creates a worktree, generates `.wad-env` + `.wad-compose.yml`, starts container
  - `start/stop/rm/ls/shell/logs/run` — manage environments/services
  - `agent start/attach/stop/status` — manage goose+tmux inside the devcontainer
- `README.md`
  Canonical usage docs.
- `install.sh`
  Copies `wad` to the install directory and checks dependencies.
- `LICENSE`

### Files generated in *target project repos* (not this repo)

When a user runs `wad init` inside some project repo, WAD creates:

- `.wad/config.yml`
  WAD config (ports, services, agent settings). Parsed via simple awk-based YAML logic.
- `.wad/compose.yml`
  Docker compose template (with `${repo_root}`, `${worktree_path}`, `${env_name}`, `${WAD_PORT_*}` variables).
- `.wad/.env`
  gitignored env vars loaded by `wad run` into service processes.
- `.wad/agent.env`
  gitignored env vars for goose/provider/model settings.
- `.wad/goose/config.yaml`
  goose config copied into the container on startup.

When a user runs `wad new <env>` WAD creates:

- `.worktrees/<env>/.wad-env`
  Computed env + port mapping variables.
- `.worktrees/<env>/.wad-compose.yml`
  Generated compose file (template with substitutions).

---

## Common workflows / commands

### Initialize WAD in a project repo

```bash
cd /path/to/your-project
wad init
# edit .wad/config.yml and .wad/compose.yml
```

### Create a new isolated environment

```bash
wad new feature-x
# creates git branch wad/feature-x + worktree at .worktrees/feature-x
# generates .wad-env and .wad-compose.yml
# docker compose up -d
```

### Start/stop and shell into the environment

```bash
wad start feature-x
wad shell feature-x
wad stop feature-x
```

### Run project services inside the devcontainer

`wad run` reads `.wad/config.yml` and starts configured services in the container (backgrounded, logs redirected):

```bash
wad run feature-x
wad logs feature-x         # compose logs
wad logs feature-x app     # tails /tmp/app.log (or configured log path)
```

### Start/attach to the coding agent

Agent is **goose**, run inside tmux in the devcontainer:

```bash
wad agent start feature-x "help me understand this repo"
wad agent attach feature-x
wad agent status feature-x
wad agent stop feature-x
```

---

## Implementation notes (for agents modifying `wad`)

### Entry point

`wad` is a Bash script with a `case` dispatcher at the bottom:

- `cmd_init`, `cmd_new`, `cmd_ls`, `cmd_start`, `cmd_stop`, `cmd_rm`, `cmd_shell`, `cmd_run`, `cmd_logs`
- agent commands: `cmd_agent_start`, `cmd_agent_attach`, `cmd_agent_stop`, `cmd_agent_status`

### YAML parsing

`wad` uses **minimal, non-general YAML parsing** for `.wad/config.yml`:

- `yaml_get` supports *simple nested maps* via dot paths (e.g. `agent.type`)
- several sections (`services`, `ports`) are parsed with ad-hoc `awk` blocks

Be careful: complex YAML (arrays, multi-line strings, anchors) may break parsing. Keep `.wad/config.yml` simple.

### Compose generation

Compose generation is **sed-based substitution** over `.wad/compose.yml`:

- substitutes `${repo_root}`, `${worktree_path}`, `${env_name}`
- substitutes `${WAD_PORT_*}` from `.wad-env`
- expands `~/` to `$HOME/`

If you add new template variables, update `generate_compose()` accordingly.

### Devcontainer command

The default template uses `python:3.12-slim` and runs a long `bash -lc` command that:

- installs packages (curl, tmux, etc.) if missing
- downloads the correct goose binary for arch (x86_64/aarch64)
- copies `/workspace/.wad/goose` into `/root/.config/goose` (copy semantics)
- touches `/tmp/wad-ready` and then `sleep infinity`

Agent/tmux helper `ensure_tmux_in_container()` waits for `/tmp/wad-ready` to avoid apt lock races.

---

## Safety / gotchas

- `wad rm <env>` may need to delete root-owned files created by containers on bind mounts.
  It tries `git worktree remove`, and if that fails it runs an `alpine` container to delete **uid 0-owned** paths before retrying.

- `wad agent attach` requires a real TTY (it uses `tmux attach` inside `docker compose exec`).

- Goose config is copied into the container (not bind-mounted). Changing `/root/.config/goose` inside the container does **not** sync back.

---

## How to validate changes

There is no formal test suite in this repo. Suggested manual checks after editing `wad`:

1. Shellcheck-style sanity (if you have it):

   ```bash
   shellcheck wad install.sh
   ```

2. End-to-end smoke test in a throwaway git repo:

   ```bash
   mkdir -p /tmp/wad-smoke && cd /tmp/wad-smoke
   git init
   echo "hello" > README.md
   git add README.md && git commit -m "init"

   /path/to/this/repo/wad init
   /path/to/this/repo/wad new test-env
   /path/to/this/repo/wad start test-env
   /path/to/this/repo/wad shell test-env
   /path/to/this/repo/wad rm test-env --force
   ```

3. If touching agent features, also:

   ```bash
   wad agent start test-env "say hello"
   wad agent status test-env
   wad agent stop test-env
   ```

---

## Contribution notes

- This repo currently contains no CI config and no explicit formatting/linting tooling.
- Keep changes minimal and well-documented in `README.md` when user-facing behavior changes.
- Prefer robust behavior over clever parsing: most failures should produce clear `die "..."` messages.
