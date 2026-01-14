# WAD - Worktree Agent Devcontainers

Isolated development environments using git worktrees and Docker.

## What it does

- Creates git worktrees for parallel development
- Runs each worktree in a devcontainer (add sidecars like postgres via `.wad/compose.yml`)
- Keeps each environment isolated via a dedicated Docker network
- Starts an interactive coding agent session (goose) inside the devcontainer

## Requirements

- git
- docker with compose
- curl

## Installation

```bash
git clone https://github.com/aron98/wad.git
cd wad
./install.sh
```

## Quick Start

```bash
cd your-project
wad init                    # Creates .wad/config.yml
# Edit .wad/config.yml for your project
wad new feature-x           # Create environment
wad run feature-x           # Start services
wad agent start feature-x "help me understand this repo"   # Start coding agent session
wad agent attach feature-x                           # Attach/reconnect to agent (interactive TTY)
```

## Commands

| Command | Description |
|---------|-------------|
| `wad init` | Initialize wad in current repo |
| `wad new <name>` | Create new environment |
| `wad ls` | List environments |
| `wad start <name>` | Start containers |
| `wad stop <name>` | Stop containers |
| `wad rm <name>` | Remove environment |
| `wad shell <name>` | Enter container bash |
| `wad run <name>` | Start services |
| `wad logs <name> [svc]` | View logs |
| `wad agent start <env> "<prompt>"` | Start (or reuse) the coding agent tmux session and send a prompt |
| `wad agent attach <env>` | Attach to the agent tmux session (requires a real TTY) |
| `wad agent status <env>` | Print `running`/`stopped` |
| `wad agent stop <env>` | Stop the agent tmux session |

## Configuration

After `wad init`, edit `.wad/config.yml`:

```yaml
version: 2

worktrees:
  # Optional. If omitted, wad will use your current branch, then main/master, then HEAD.
  default_base: main

ports:
  increment: 10
  exposed:
    APP: 8080

services:
  app:
    name: app
    workdir: /workspace
    command: python main.py
    log: /tmp/app.log

# Coding agent (runs inside the devcontainer)
agent:
  # For now, only `goose` is supported.
  type: goose

  # Extra env vars for the agent (gitignored by default)
  env_file: .wad/agent.env

  # tmux session name used for start/attach/stop
  session_name: wad-agent

  goose:
    # Directory copied into /root/.config/goose at container start
    config_dir: .wad/goose
```

### Coding agent environment

Edit `.wad/agent.env` (created by `wad init`, gitignored by default). Put your provider/model/etc here.
For example, for goose:

```bash
# .wad/agent.env
GOOSE_PROVIDER=...
GOOSE_MODEL=...
```

### Goose configuration

`wad init` creates `.wad/goose/` (gitignored by default). At **container start**, the devcontainer copies that directory into:

- `/root/.config/goose`

So you can commit safe defaults in `.wad/goose` (if you choose to), or keep it untracked for local-only provider/model settings.

Note: because this is **copy** semantics (not a bind mount), edits made inside the container to `/root/.config/goose` will not sync back to your repo.

### Attaching and logs
`wad agent attach <env>` attaches you to the **interactive goose session** (the tmux window named `agent`).

The tmux session also creates a `logs` window that tails service log files:
- If you set `services.<name>.log` in `.wad/config.yml`, it will tail that.
- Otherwise it defaults to `/tmp/<service>.log`.

To switch windows while attached:
- `Ctrl+b` then `1` → `logs`
- `Ctrl+b` then `0` → `agent`

For the agent to see app console output reliably, start services via `wad run`.

## How it works

1. `wad new` creates a git worktree and generates a docker-compose file
2. The devcontainer mounts your worktree and shared dependencies
3. `wad run` starts your services inside the container
4. `wad agent start` starts a tmux-based coding agent session inside the devcontainer

## License

MIT
