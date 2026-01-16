#!/usr/bin/env bash
#
# WAD Installer
#
# Supports two modes:
#   1) Local (run from a cloned repo): ./install.sh
#   2) Remote (curl | bash):          curl -fsSL <url>/install.sh | bash
#
# By default installs to: ~/.local/bin
# Override with: WAD_INSTALL_DIR=/some/dir
#
# Optional overrides for remote installs:
#   WAD_GITHUB_REPO=owner/repo   (default: aron98/wad)
#   WAD_REF=main|vX.Y.Z|<sha>    (default: main)
#

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1" >&2; }

die() {
    log_error "$1"
    exit 1
}

INSTALL_DIR="${WAD_INSTALL_DIR:-$HOME/.local/bin}"
XDG_DATA_HOME_DEFAULT="${XDG_DATA_HOME:-$HOME/.local/share}"
WAD_GITHUB_REPO="${WAD_GITHUB_REPO:-aron98/wad}"
WAD_REF="${WAD_REF:-main}"

# When run via `curl ... | bash`, BASH_SOURCE may be unset; fall back to $0.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

banner() {
    echo ""
    echo "  ╔════════════════════════════════════════╗"
    echo "  ║   WAD - Worktree Agent Devcontainers   ║"
    echo "  ║   Isolated dev environments with       ║"
    echo "  ║   git worktrees and Docker             ║"
    echo "  ╚════════════════════════════════════════╝"
    echo ""
}

check_cmd() {
    if command -v "$1" &>/dev/null; then
        return 0
    fi
    return 1
}

require_cmd() {
    local cmd="$1"
    local hint="${2:-}"
    if ! check_cmd "$cmd"; then
        if [[ -n "$hint" ]]; then
            die "$cmd not found. $hint"
        fi
        die "$cmd not found."
    fi
}

# Global state set by resolve_source_dir
SOURCE_DIR=""
TMP_DIR=""

# Sets SOURCE_DIR to a directory that contains: wad, completions/wad.bash, wad_mcp_server/
# If a remote archive is downloaded, TMP_DIR is set and will be cleaned up via trap.
resolve_source_dir() {
    # Local install: adjacent to this script.
    if [[ -f "$SCRIPT_DIR/wad" ]]; then
        SOURCE_DIR="$SCRIPT_DIR"
        return 0
    fi

    # Remote install (curl|bash): download an archive and extract it.
    require_cmd curl "Install curl and re-run."
    require_cmd tar "Install tar and re-run."

    TMP_DIR="$(mktemp -d)"
    # Clean up on exit (success or failure).
    # shellcheck disable=SC2064
    trap "rm -rf '$TMP_DIR'" EXIT

    local url
    url="https://github.com/${WAD_GITHUB_REPO}/archive/${WAD_REF}.tar.gz"

    log_info "Fetching WAD from ${WAD_GITHUB_REPO}@${WAD_REF}..." >&2
    if ! curl -fsSL "$url" -o "$TMP_DIR/wad.tar.gz"; then
        die "Failed to download: $url"
    fi

    tar -xzf "$TMP_DIR/wad.tar.gz" -C "$TMP_DIR"

    # GitHub archives contain a single top-level directory. Our temp dir also
    # contains the downloaded tarball, so explicitly pick the first directory.
    local top_dir=""
    local p
    for p in "$TMP_DIR"/*; do
        if [[ -d "$p" ]]; then
            top_dir="$p"
            break
        fi
    done

    if [[ -z "$top_dir" || ! -d "$top_dir" ]]; then
        die "Failed to unpack WAD archive"
    fi

    SOURCE_DIR="$top_dir"
}

install_file() {
    # install_file <src> <dest>
    local src="$1"
    local dest="$2"

    mkdir -p "$(dirname "$dest")"

    if check_cmd install; then
        install -m 0755 "$src" "$dest"
    else
        cp "$src" "$dest"
        chmod 0755 "$dest"
    fi
}

main() {
    banner

    # Minimal install-time deps. (git/docker are runtime deps for using wad, not for installing it.)
    # Don't force-install runtime deps here; keep installer lightweight.
    # We do require a few core utilities.
    require_cmd mkdir
    require_cmd cp
    require_cmd chmod

    resolve_source_dir

    if [[ -z "$SOURCE_DIR" ]]; then
        die "Failed to resolve installer source directory"
    fi

    if [[ ! -f "$SOURCE_DIR/wad" ]]; then
        die "Installer source is missing 'wad' (source_dir=$SOURCE_DIR)"
    fi

    log_info "Installing to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"

    install_file "$SOURCE_DIR/wad" "$INSTALL_DIR/wad"
    log_success "Installed: $INSTALL_DIR/wad"

    # Install the MCP server (vendored) so users can run `wad mcp` without pip-installing this repo.
    # We intentionally do not require Python as an install-time dependency for *core* WAD usage.
    local mcp_src
    mcp_src="$SOURCE_DIR/wad_mcp_server"

    local mcp_dest
    mcp_dest="${XDG_DATA_HOME_DEFAULT}/wad-mcp-server"

    if [[ -d "$mcp_src" ]]; then
        log_info "Installing MCP server (vendored) to $mcp_dest..."
        mkdir -p "$mcp_dest"
        rm -rf "$mcp_dest/wad_mcp_server"
        cp -R "$mcp_src" "$mcp_dest/"
        log_success "MCP server code installed: $mcp_dest/wad_mcp_server"

        # Install MCP Python dependency into an isolated venv to avoid system-Python/PEP-668 issues.
        if command -v python3 >/dev/null 2>&1; then
            if python3 -m venv --help >/dev/null 2>&1; then
                local mcp_venv
                mcp_venv="$mcp_dest/venv"

                log_info "Setting up MCP Python venv at $mcp_venv..."
                python3 -m venv "$mcp_venv" || log_warn "Failed to create venv at $mcp_venv (wad mcp may still work if fastmcp is installed elsewhere)"

                if [[ -x "$mcp_venv/bin/python" ]]; then
                    "$mcp_venv/bin/python" -m pip --version >/dev/null 2>&1 || "$mcp_venv/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
                    "$mcp_venv/bin/python" -m pip install -q --upgrade pip >/dev/null 2>&1 || true

                    log_info "Installing MCP dependency: fastmcp>=2.14.0 (venv scope)"
                    if "$mcp_venv/bin/python" -m pip install -q "fastmcp>=2.14.0"; then
                        log_success "MCP dependency installed (venv): fastmcp"
                    else
                        log_warn "Failed to install fastmcp into venv. You can install it manually: $mcp_venv/bin/python -m pip install 'fastmcp>=2.14.0'"
                    fi
                fi
            else
                log_warn "python3 is available but venv support is missing; skipping MCP venv setup"
            fi
        else
            log_warn "python3 not found; skipping MCP dependency install (wad mcp will require Python)"
        fi
    else
        log_warn "MCP server directory not found in source; skipping MCP install"
    fi

    # Install bash completion (user-scope)
    local completion_dir
    completion_dir="$XDG_DATA_HOME_DEFAULT/bash-completion/completions"
    if [[ -f "$SOURCE_DIR/completions/wad.bash" ]]; then
        mkdir -p "$completion_dir"
        cp "$SOURCE_DIR/completions/wad.bash" "$completion_dir/wad"
        log_success "Bash completion installed: $completion_dir/wad"
    else
        log_warn "Bash completion script not found (expected: $SOURCE_DIR/completions/wad.bash)"
    fi

    # PATH hint
    if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
        log_warn "$INSTALL_DIR is not in your PATH"
        echo ""
        echo "Add this to your shell config (~/.bashrc or ~/.zshrc):"
        echo ""
        echo "    export PATH=\"\$PATH:$INSTALL_DIR\""
        echo ""
    fi

    # Friendly runtime dependency reminder.
    if ! command -v git >/dev/null 2>&1; then
        log_warn "git not found (required to use wad in project repos)"
    fi
    if ! command -v docker >/dev/null 2>&1; then
        log_warn "docker not found (required to use wad devcontainers)"
    elif ! docker compose version >/dev/null 2>&1; then
        log_warn "docker compose not found (required to use wad devcontainers)"
    fi

    log_success "Installation complete!"
    echo ""
    echo "Usage:"
    echo "  cd your-project"
    echo "  wad init                        # Initialize (creates .wad/config.yml)"
    echo "  # Edit .wad/config.yml for your project"
    echo "  wad new <env> [prompt...]        # Create environment (optionally start goose)"
    echo "  wad run <env>                    # Start services"
    echo "  wad agent <env> \"help me understand this repo\"  # Start goose for an existing environment"
    echo "  wad attach <env>                 # Attach/reconnect (interactive TTY)"
    echo "  wad mcp                          # Start the WAD MCP server (stdio)"
    echo "  wad help                         # Show all commands"
    echo ""
}

main "$@"
