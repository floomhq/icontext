#!/usr/bin/env bash
# fbrain installer
# Usage: curl -fsSL https://raw.githubusercontent.com/floomhq/fbrain/main/get.sh | bash

set -euo pipefail

FBRAIN_DIR="${FBRAIN_DIR:-${ICONTEXT_DIR:-$HOME/fbrain}}"
BIN_DIR="$HOME/.local/bin"

echo "fbrain: installing..."

# --- Dependency checks -------------------------------------------------------
MISSING_DEPS=()

if ! command -v git &>/dev/null; then
    MISSING_DEPS+=("git")
fi

if ! command -v python3 &>/dev/null; then
    MISSING_DEPS+=("python3")
fi

if [ "${#MISSING_DEPS[@]}" -gt 0 ]; then
    echo ""
    echo "fbrain: missing required tools: ${MISSING_DEPS[*]}"
    echo ""
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "On Mac, install them with:"
        for dep in "${MISSING_DEPS[@]}"; do
            case "$dep" in
                git)    echo "  xcode-select --install   (installs git + other dev tools)" ;;
                python3) echo "  brew install python3     (or: xcode-select --install)" ;;
            esac
        done
    else
        echo "Install with your package manager, e.g.:"
        echo "  sudo apt install git python3"
    fi
    echo ""
    echo "Then re-run: curl -fsSL https://raw.githubusercontent.com/floomhq/fbrain/main/get.sh | bash"
    exit 1
fi
# -----------------------------------------------------------------------------

# Clone or update
if [ -d "$FBRAIN_DIR/.git" ]; then
    echo "fbrain: updating $FBRAIN_DIR"
    git -C "$FBRAIN_DIR" pull --ff-only --quiet
else
    echo "fbrain: cloning to $FBRAIN_DIR"
    git clone --quiet https://github.com/floomhq/fbrain "$FBRAIN_DIR"
fi

# Install CLI
# Note: in agents mode, install.sh creates a symlink from ~/.local/bin/fbrain
# into the vault AFTER the vault is created by `fbrain init`. We install a
# direct symlink to the repo here so the CLI is available immediately.
mkdir -p "$BIN_DIR"
if command -v pip3 &>/dev/null && pip3 install -e "$FBRAIN_DIR" --quiet 2>/dev/null; then
    echo "fbrain: CLI installed via pip"
else
    ln -sf "$FBRAIN_DIR/cli.py" "$BIN_DIR/fbrain"
    ln -sf "$FBRAIN_DIR/cli.py" "$BIN_DIR/icontext"
    chmod +x "$FBRAIN_DIR/cli.py"
    echo "fbrain: CLI linked to $BIN_DIR/fbrain"
fi

# Auto-add ~/.local/bin to PATH in shell profile
SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -f "$HOME/.bash_profile" ]; then
    SHELL_RC="$HOME/.bash_profile"
fi

if [ -n "$SHELL_RC" ]; then
    if ! grep -q 'local/bin' "$SHELL_RC" 2>/dev/null; then
        echo '' >> "$SHELL_RC"
        echo '# fbrain' >> "$SHELL_RC"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        echo "fbrain: added ~/.local/bin to PATH in $SHELL_RC"
    fi
fi

echo ""
echo "fbrain: done."
echo ""
echo "  Next:"
echo "    1. Restart your terminal (or: source ~/.zshrc)"
echo "    2. Run: fbrain init"
echo "    3. Open Claude Code and say: \"populate my fbrain profile\""
echo ""
echo "  No API keys needed. Your agent does the synthesis."
