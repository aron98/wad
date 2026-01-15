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

_wad__list_envs() {
  # Prefer repo-local .worktrees/<env>/ directories when inside a wad-initialized repo.
  local repo_root
  repo_root=$(_wad__repo_root) || return 0

  local wt_dir="$repo_root/.worktrees"
  [[ -d "$wt_dir" ]] || return 0

  local d
  for d in "$wt_dir"/*; do
    [[ -d "$d" ]] || continue
    basename "$d"
  done
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
