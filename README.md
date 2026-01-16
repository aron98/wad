# WAD - Worktree Agent Devcontainers

Isolated development environments using git worktrees and Docker.

## What it does

- Creates git worktrees for parallel development
- Runs each worktree in a devcontainer (add sidecars like postgres via `.wad/compose.yml`)
- Keeps each environment isolated via a dedicated Docker network
- Runs a background **goose** task inside the devcontainer (non-interactive `goose run --no-session --recipe ...`) and lets you attach

## Requirements

- git
- docker with compose
- curl

## Installation

### One-line installer (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/aron98/wad/main/install.sh | bash
```

Options:

- Install to a custom directory:

```bash
WAD_INSTALL_DIR="$HOME/bin" curl -fsSL https://raw.githubusercontent.com/aron98/wad/main/install.sh | bash
```

- Install a specific ref (tag/branch/SHA):

```bash
WAD_REF=v0.1.0 curl -fsSL https://raw.githubusercontent.com/aron98/wad/main/install.sh | bash
```

### Install from a clone (developer-friendly)

```bash
git clone https://github.com/aron98/wad.git
cd wad
./install.sh
```

## Quick Start

```bash
cd your-project
wad init
# Edit .wad/compose.yml (your devcontainer + sidecars)
# Edit .wad/config.yml (ports, services, goose settings)

wad new feature-x

wad agent feature-x "add a healthcheck endpoint and tests"

wad attach <env>                     # watch goose + logs (tmux)
wad status <env>                     # check goose completion + show JSON result (if any)
wad logs <env> --tail 200            # print recent docker compose logs and exit
wad logs <env> goose --tail 200      # print recent /tmp/goose.log content and exit
wad logs <env> --follow              # stream docker compose logs (interactive)
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
| `wad logs <env> [svc|goose] [--tail N] [--follow]` | View logs (default: prints and exits; use `--follow` to stream). Uses `docker compose logs --no-color --tail N` and best-effort file reads for `goose`/services. |

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

## MCP server (local stdio)

This repo also includes a **local stdio MCP server** that exposes `wad` operations over MCP so agents can create/manage environments.

- Transport: **stdio** (intended to be launched by an MCP-capable client)
- Implementation: **Python** using **FastMCP v2** (`fastmcp` on PyPI)
- Long-running operations (`wad new`, `wad start`, `wad rm`, `wad run`, `wad agent`) support **MCP background tasks** via FastMCP's `task` configuration.

### Task status / progress updates (server-side)

When a tool is invoked as an MCP background task (SEP-1686), FastMCP exposes task progress via:

- `tasks/get` (polling)
- optional server `notifications/tasks/status`

WAD adds **fine-grained, machine-readable status updates** by emitting status markers from the `wad` bash script and translating them into the MCP task `statusMessage`.

#### Status encoding

Each update is a JSON object embedded into the MCP task `statusMessage` string:

```json
{"namespace":"wad","code":"env.devcontainer_ready","state":"starting","message":"Waiting for devcontainer readiness","step":6,"total":8,"ts":"2026-01-16T09:38:00+00:00"}
```

Fields:

- `namespace`: always `"wad"`
- `code`: stable machine-readable phase identifier
- `state`: one of `starting | running | completed | failed`
- `message`: human-friendly summary
- `step` / `total`: optional step progress (for UIs)
- `ts`: server timestamp (RFC3339)

#### Emitted phase codes

Environment creation (`wad_new`) emits the following `code` values:

1. `env.create`
2. `env.worktree`
3. `env.compose`
4. `env.containers`
5. `env.devcontainer_ready`
6. `services.start`
7. `agent.start` (only if a prompt was provided)
8. `agent.running` (only if a prompt was provided)

Agent start (`wad_agent`) emits:

- `agent.start`
- `env.containers` (only if containers must be started)
- `env.devcontainer_ready`
- `agent.running`

Agent completion (`wad_agent_wait`) emits:

- `agent.start`
- `agent.running`
- `agent.finished` or `agent.failed`

#### Client subscription guidance

How clients can consume updates:

- **Recommended**: call task-enabled tools as background tasks, then listen for `notifications/tasks/status` (if your MCP client surfaces them) or poll `tasks/get`.
- `tasks/get` will return a `statusMessage` string; if it starts with `{`, parse it as JSON and read the fields above.

Notes:

- WAD enables status markers only when invoked via the MCP server (it sets `WAD_MCP_STATUS=1`). Normal CLI output remains unchanged.
- Tool return payloads include a `last_status` field (best-effort) for convenience if clients did not subscribe during execution.

### Install (dev)

```bash
python -m pip install -e .
```

### Run

From the project repo you want to control:

```bash
wad mcp
```

### Smoke test / manual reproduction (status updates)

Because this repo has no automated test suite, here are manual steps to verify MCP task status updates.

#### 1) Create a throwaway git repo

```bash
mkdir -p /tmp/wad-smoke && cd /tmp/wad-smoke
git init
printf "hello\n" > README.md
git add README.md && git commit -m "init"

# Use this repo's wad script
/path/to/this/repo/wad init
```

#### 2) Run the MCP server

```bash
/path/to/this/repo/wad mcp --project-root /tmp/wad-smoke --wad-bin /path/to/this/repo/wad
```

#### 3) From an MCP client

- Call `wad_new(env="test-env")` as a background task.
- Observe `tasks/get` returning a `statusMessage` string containing JSON.
- Optionally observe `notifications/tasks/status` if your client surfaces them.

Expected progression (example):

- `env.create` → `env.worktree` → `env.compose` → `env.containers` → `env.devcontainer_ready` → `services.start`

If you pass a prompt to `wad_new(env="test-env", prompt="...")`, you should additionally see:

- `agent.start` → `agent.running`

To test agent completion end-to-end in one task, call:

- `wad_agent_wait(env="test-env", prompt="say hello")`

Expected final status:

- `agent.finished` (or `agent.failed`)

Notes:

- Some MCP clients (or SDKs) do not yet route task status notifications to a callback; in that case, polling `tasks/get` is sufficient.
- Docker pulls and container setup can take several minutes on first run.


This is a convenience wrapper that:

- uses `wad-mcp-server` if it's installed in your current Python environment, otherwise
- runs a **vendored copy** of the MCP server that ships with WAD (installed by `install.sh`),
  and prefers the isolated venv at `~/.local/share/wad-mcp-server/venv` if present.

#### Environment variables

- `WAD_PROJECT_ROOT`: project directory to run `wad` in (defaults to current working directory)
- `WAD_BIN`: explicit path to the `wad` executable (defaults to `./wad` if present, otherwise `wad` from `$PATH`)

#### MCP client/provider configuration

Because this server uses **stdio**, most MCP clients configure it as a command + args. Example (pseudo-config):

```json
{
  "mcpServers": {
    "wad": {
      "command": "wad",
      "args": ["mcp"],
      "env": {
        "WAD_PROJECT_ROOT": "/path/to/your-project"
      }
    }
  }
}
```

### Exposed tools

- `wad_init(mode?, repo_path?)`
- `wad_new(env, prompt?, repo_path?)` (task-capable)
- `wad_start(env, repo_path?)` (task-capable)
- `wad_stop(env, repo_path?)` (task-capable)
- `wad_rm(env, repo_path?)` (task-capable)
- `wad_ls(repo_path?)`
- `wad_run(env, repo_path?)` (task-capable)
- `wad_logs(env, service?, repo_path?, timeout_s=5)` (task-capable; uses timeout by default to avoid infinite follow)
- `wad_status(env, repo_path?)` (task-capable; best-effort JSON parsing)
- `wad_agent(env, prompt, repo_path?)` (task-capable)
- `wad_agent_wait(env, prompt, repo_path?, poll_interval_s=2.0, timeout_s?)` (task-capable; starts agent and waits for completion)

### Notes

- `wad` itself expects to be run in a **git repository**. If you point `WAD_PROJECT_ROOT` at a non-git directory, commands will fail.
- This server does not currently strip WAD's ANSI color codes; most clients can handle them, but you may want to keep outputs short.

## Shell completion

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

## License

MIT
