# WAD - Worktree Agent Devcontainers

Isolated development environments using git worktrees and Docker.

## What it does

- Creates git worktrees for parallel development
- Runs each worktree in a devcontainer with sidecars (postgres, etc)
- Mounts your existing dependencies (venv, node_modules)
- Starts goose sessions

## Requirements

- git
- docker with compose
- curl

## Installation

```bash
git clone https://github.com/youruser/wad.git
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
wad attach feature-x        # Start goose session
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
| `wad attach <name>` | Start goose session |
| `wad logs <name> [svc]` | View logs |

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
```

## How it works

1. `wad new` creates a git worktree and generates a docker-compose file
2. The devcontainer mounts your worktree and shared dependencies
3. `wad run` starts your services inside the container
4. `wad attach` starts goose inside the devcontainer

## License

MIT
