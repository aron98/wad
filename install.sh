#!/usr/bin/env bash
#
# WAD Installer
# Installs wad to ~/.local/bin
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1" >&2; }

INSTALL_DIR="${WAD_INSTALL_DIR:-$HOME/.local/bin}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
XDG_DATA_HOME_DEFAULT="${XDG_DATA_HOME:-$HOME/.local/share}"

echo ""
echo "  ╔════════════════════════════════════════╗"
echo "  ║   WAD - Worktree Agent Devcontainers   ║"
echo "  ║   Isolated dev environments with       ║"
echo "  ║   git worktrees and Docker             ║"
echo "  ╚════════════════════════════════════════╝"
echo ""

# Check dependencies
log_info "Checking dependencies..."

check_cmd() {
    if command -v "$1" &> /dev/null; then
        log_success "$1 found"
        return 0
    else
        log_error "$1 not found"
        return 1
    fi
}

deps_ok=true
check_cmd git || deps_ok=false
check_cmd docker || deps_ok=false
docker compose version &>/dev/null || { log_error "docker compose not found"; deps_ok=false; }
check_cmd curl || deps_ok=false

if [[ "$deps_ok" != "true" ]]; then
    echo ""
    log_error "Missing dependencies. Please install them and try again."
    exit 1
fi

echo ""

# Create install directory
log_info "Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Copy wad script
cp "$SCRIPT_DIR/wad" "$INSTALL_DIR/wad"
chmod +x "$INSTALL_DIR/wad"


# Ensure WAD config root exists (used for default worktree storage)
XDG_CONFIG_HOME_DEFAULT="${XDG_CONFIG_HOME:-$HOME/.config}"
mkdir -p "$XDG_CONFIG_HOME_DEFAULT/wad"
log_success "WAD config root ready: $XDG_CONFIG_HOME_DEFAULT/wad"

# Install the MCP server (vendored) so users can run `wad mcp` without pip-installing this repo.
# We intentionally do not require Python as an install-time dependency for *core* WAD usage,
# but we *do* try to set up the MCP runtime so `wad mcp` works out-of-the-box.
MCP_DEST="${XDG_DATA_HOME_DEFAULT}/wad-mcp-server"
log_info "Installing MCP server (vendored) to $MCP_DEST..."
mkdir -p "$MCP_DEST"
rm -rf "$MCP_DEST/wad_mcp_server"
cp -R "$SCRIPT_DIR/wad_mcp_server" "$MCP_DEST/"
log_success "MCP server code installed: $MCP_DEST/wad_mcp_server"

# Install MCP Python dependency into an isolated venv to avoid system-Python/PEP-668 issues.
# This keeps the host environment clean and makes `wad mcp` reliable.
if command -v python3 >/dev/null 2>&1; then
    if python3 -m venv --help >/dev/null 2>&1; then
        MCP_VENV="$MCP_DEST/venv"
        log_info "Setting up MCP Python venv at $MCP_VENV..."
        python3 -m venv "$MCP_VENV" || log_warn "Failed to create venv at $MCP_VENV (wad mcp may still work if fastmcp is installed elsewhere)"

        if [[ -x "$MCP_VENV/bin/python" ]]; then
            # Ensure pip exists in the venv, then install fastmcp.
            "$MCP_VENV/bin/python" -m pip --version >/dev/null 2>&1 || "$MCP_VENV/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
            "$MCP_VENV/bin/python" -m pip install -q --upgrade pip >/dev/null 2>&1 || true

            log_info "Installing MCP dependency: fastmcp>=2.14.0 (venv scope)"
            if "$MCP_VENV/bin/python" -m pip install -q "fastmcp>=2.14.0"; then
                log_success "MCP dependency installed (venv): fastmcp"
            else
                log_warn "Failed to install fastmcp into venv. You can install it manually: $MCP_VENV/bin/python -m pip install 'fastmcp>=2.14.0'"
            fi
        fi
    else
        log_warn "python3 is available but venv support is missing; skipping MCP venv setup"
    fi
else
    log_warn "python3 not found; skipping MCP dependency install (wad mcp will require Python)"
fi

# Install bash completion (user-scope)
COMPLETION_DIR="$XDG_DATA_HOME_DEFAULT/bash-completion/completions"
if [[ -f "$SCRIPT_DIR/completions/wad.bash" ]]; then
    mkdir -p "$COMPLETION_DIR"
    cp "$SCRIPT_DIR/completions/wad.bash" "$COMPLETION_DIR/wad"
    log_success "Bash completion installed: $COMPLETION_DIR/wad"
else
    log_warn "Bash completion script not found (expected: $SCRIPT_DIR/completions/wad.bash)"
fi

# Check PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    log_warn "$INSTALL_DIR is not in your PATH"
    echo ""
    echo "Add this to your shell config (~/.bashrc or ~/.zshrc):"
    echo ""
    echo "    export PATH=\"\$PATH:$INSTALL_DIR\""
    echo ""
fi

log_success "Installation complete!"
echo ""
echo "Usage:"
echo "  cd your-project"
echo "  wad init              # Initialize (creates .wad/config.yml)"
echo "  # Edit .wad/config.yml for your project"
echo "  wad new <env> [prompt...]    # Create environment (optionally start goose)"
echo "  wad run <env>                # Start services"
echo "  wad agent <env> \"help me understand this repo\"  # Start goose for an existing environment"
echo "  wad attach <env>             # Attach/reconnect (interactive TTY)"
echo "  wad mcp                      # Start the WAD MCP server (stdio)"
echo "  wad help              # Show all commands"
echo ""
