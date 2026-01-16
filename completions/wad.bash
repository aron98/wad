# Bash completion for wad
#
# Install:
#   mkdir -p ~/.local/share/bash-completion/completions
#   cp completions/wad.bash ~/.local/share/bash-completion/completions/wad
#   # restart shell (or: source the file)
#
# Notes:
# - Works best with bash-completion.
# - For zsh: enable bash completion emulation:
#     autoload -Uz bashcompinit && bashcompinit
#     source ~/.local/share/bash-completion/completions/wad

_wad__repo_root() {
  git rev-parse --show-toplevel 2>/dev/null
}

_wad__slugify() {
  # Minimal slugify matching wad's behavior (approx).
  local s="$*"
  s=$(printf '%s' "$s" | tr '[:upper:]' '[:lower:]')
  s=$(printf '%s' "$s" | sed -E 's/[^a-z0-9]+/-/g; s/-+/-/g; s/^-+//; s/-+$//')
  s=$(printf '%s' "$s" | cut -c1-48)
  [[ -z "$s" ]] && s="env"
  printf '%s' "$s"
}

_wad__worktrees_base_dir() {
  local repo_root="$1"

  local cfg="$repo_root/.wad/config.yml"
  local base_dir=""

  # Parse worktrees.base_dir from config.yml (simple nested map).
  if [[ -f "$cfg" ]]; then
    base_dir=$(awk '
      function trim(s){ sub(/^[ \t]+/,"",s); sub(/[ \t]+$/,"",s); return s }
      BEGIN{ in=0 }
      /^worktrees:[[:space:]]*$/ { in=1; next }
      in && /^[^[:space:]]/ { exit }
      in && /^[[:space:]]{2}base_dir:[[:space:]]*/ {
        v=$0; sub(/^[[:space:]]{2}base_dir:[[:space:]]*/,"",v);
        v=trim(v);
        sub(/^\"/,"",v); sub(/\"$/,"",v);
        sub(/^\x27/,"",v); sub(/\x27$/,"",v);
        print v; exit
      }
    ' "$cfg" 2>/dev/null)
  fi

  # Allow env var override.
  if [[ -n "${WAD_WORKTREES_BASE_DIR:-}" ]]; then
    base_dir="$WAD_WORKTREES_BASE_DIR"
  fi

  if [[ -z "$base_dir" ]]; then
    local slug
    slug=$(_wad__slugify "$(basename "$repo_root")")
    base_dir="${XDG_CONFIG_HOME:-$HOME/.config}/wad/${slug}/worktrees"
  fi

  # Expand ~
  if [[ "$base_dir" == "~" ]]; then
    base_dir="$HOME"
  elif [[ "$base_dir" == "~/"* ]]; then
    base_dir="$HOME/${base_dir#~/}"
  fi

  # Relative paths are relative to repo_root.
  if [[ "$base_dir" != /* ]]; then
    base_dir="$repo_root/$base_dir"
  fi

  printf '%s' "$base_dir"
}

_wad__list_envs() {
  # List envs from the preferred base dir, plus legacy .worktrees for backwards compatibility.
  local repo_root
  repo_root=$(_wad__repo_root) || return 0

  local base_dir legacy_dir
  base_dir=$(_wad__worktrees_base_dir "$repo_root")
  legacy_dir="$repo_root/.worktrees"

  local d

  if [[ -d "$base_dir" ]]; then
    for d in "$base_dir"/*; do
      [[ -d "$d" ]] || continue
      basename "$d"
    done
  fi

  if [[ -d "$legacy_dir" ]]; then
    for d in "$legacy_dir"/*; do
      [[ -d "$d" ]] || continue
      basename "$d"
    done
  fi
}

_wad__list_services() {
  # Extract service names from .wad/config.yml (keys under `services:`).
  local repo_root
  repo_root=$(_wad__repo_root) || return 0

  local cfg="$repo_root/.wad/config.yml"
  [[ -f "$cfg" ]] || return 0

  awk '
    function ltrim(s) { sub(/^[ \t\r\n]+/, "", s); return s }
    /^services:[[:space:]]*$/ { in_services = 1; next }
    in_services && /^[^[:space:]]/ { exit }
    in_services && /^[[:space:]]{2}[A-Za-z0-9_-]+:[[:space:]]*$/ {
      line = ltrim($0)
      sub(/:.*/, "", line)
      print line
    }
  ' "$cfg" 2>/dev/null
}

_wad__prev_word() {
  local idx=$((COMP_CWORD-1))
  if (( idx >= 0 )); then
    printf '%s' "${COMP_WORDS[$idx]}"
  fi
}

_wad__complete_envs() {
  local cur="$1"
  local envs
  envs=$(_wad__list_envs)
  COMPREPLY=( $(compgen -W "$envs" -- "$cur") )
}

_wad() {
  local cur prev cmd
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev=$(_wad__prev_word)

  # Top-level commands.
  local commands="init new agent attach status ls start stop rm shell run logs mcp help version --help -h --version -v"

  if (( COMP_CWORD == 1 )); then
    COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
    return 0
  fi

  cmd="${COMP_WORDS[1]}"

  # Complete env names for commands that take <env> as the next arg.
  case "$cmd" in
    agent|attach|status|start|stop|rm|shell|run|logs)
      if (( COMP_CWORD == 2 )); then
        _wad__complete_envs "$cur"
        return 0
      fi
      ;;
  esac

  # Arg/flag completion.
  case "$cmd" in
    logs)
      # `wad logs <env> [svc|goose]`
      if (( COMP_CWORD == 3 )); then
        local opts
        opts="goose $(_wad__list_services)"
        COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
        return 0
      fi
      ;;
    rm)
      # `wad rm <env> [--force]`
      if (( COMP_CWORD >= 3 )); then
        COMPREPLY=( $(compgen -W "--force" -- "$cur") )
        return 0
      fi
      ;;
  esac

  COMPREPLY=()
}

complete -F _wad wad
