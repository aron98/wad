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
echo "  wad help              # Show all commands"
echo ""
