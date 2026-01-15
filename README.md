# Completion

WAD ships with bash tab-completion for the `wad` command.

- **Bash** (recommended):
  - Ensure `bash-completion` is installed and enabled on your system.
  - If you installed via `./install.sh`, the completion script is installed to:
    - `~/.local/share/bash-completion/completions/wad`
  - Restart your shell.

- **Zsh** (via bash completion emulation):

```zsh
autoload -Uz bashcompinit && bashcompinit
source ~/.local/share/bash-completion/completions/wad
```

This enables tab completion for:
- top-level commands (e.g. `init`, `new`, `rm`, ...)
- environment names (from `.worktrees/<env>`)
- common flags (currently `wad rm --force`)

---


# WAD - Worktree Agent Devcontainers

Isolated development environments using git worktrees and Docker.

## What it does

- Creates git worktrees for parallel development
- Runs each worktree in a devcontainer (add sidecars like postgres via `.wad/compose.yml`)
- Keeps each environment isolated via a dedicated Docker network
- Runs a **background goose task** inside the devcontainer (non-interactive `goose run --no-session --recipe ...`) and lets you attach

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

## Quick Start (new simplified flow)

```bash
cd your-project
wad init
# Edit .wad/compose.yml (your devcontainer + sidecars)
# Edit .wad/config.yml (ports, services, goose settings)

wad new feature-x

wad agent feature-x "add a healthcheck endpoint and tests"

wad attach <env>           # watch goose + logs (tmux)
wad status <env>           # check goose completion + show JSON result (if any)
wad logs <env> goose       # tail /tmp/goose.log without attaching
```

## Commands

| Command | Description |
|---------|-------------|
| `wad init` | Initialize wad in current repo (writes templates) |
| `wad new <env> [prompt...]` | Create a new environment (starts containers + services). If prompt provided, also starts goose task in background |
| `wad agent <env> <prompt...>` | Start goose for an existing environment |
| `wad attach <env>` | Attach to the tmux session inside the devcontainer (requires a real TTY) |
| `wad status <env>` | Show goose task status and (if available) the structured result JSON |
| `wad ls` | List environments |
| `wad start <env>` | Start containers |
| `wad stop <env>` | Stop containers |
| `wad rm <env> [--force]` | Remove environment |
| `wad shell <env>` | Enter container bash |
| `wad run <env>` | Start services (from config.yml) |
| `wad logs <env> [svc|goose]` | View logs (use `goose` to tail `/tmp/goose.log`) |

### Parseable env name output

`wad new` prints a final machine-parseable line:

```text
ENV=<env>
```


## Configuration

After `wad init`, edit `.wad/config.yml`:

```yaml
version: 3

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

agent:
  type: goose
  env_file: .wad/agent.env
  session_name: wad-agent
  goose:
    config_dir: .wad/goose
```

### Unattended execution (recipes)

WAD runs goose in **unattended** mode by default (no additional human input expected).

On `wad init`, WAD creates a generic recipe:

- `.wad/goose/recipes/wad_task.yaml`

On `wad new <env> "<prompt>"` (or `wad agent <env> "<prompt>"`), WAD runs:

```bash
goose run --no-session \
  --recipe /workspace/.wad/goose/recipes/wad_task.yaml \
  --params task=/tmp/wad-prompt
```

This recipe:
- instructs goose not to ask questions or wait for user input
- requires it to always finish with a structured JSON result (`completed` or `blocked`)


### Goose environment

Edit `.wad/agent.env` (created by `wad init`, gitignored by default). Put your provider/model/etc here.
For example:

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

## Attaching and logs

- Goose runs in a detached tmux session (`agent.session_name`, default `wad-agent`).
- `wad attach <env>` attaches you to the tmux session.
- The tmux session also creates a `logs` window that tails:
  - `/tmp/goose.log`
  - each configured service log file (`services.<name>.log`), or `/tmp/<service>.log` by default

To switch windows while attached:

- `Ctrl+b` then `0` → `agent`
- `Ctrl+b` then `1` → `logs`

## How it works

1. `wad new <env>` creates a git worktree at `.worktrees/<env>` with branch `wad/<env>`
2. Generates `.wad-env` and `.wad-compose.yml` for the worktree
3. Starts the devcontainer (and any sidecars)
4. Starts your configured services inside the devcontainer
5. If you provide a prompt (via `wad new <env> "<prompt>"` or `wad agent <env> "<prompt>"`), it launches `goose run --no-session --recipe /workspace/.wad/goose/recipes/wad_task.yaml --params task=/tmp/wad-prompt` inside tmux and returns immediately

## License

MIT
