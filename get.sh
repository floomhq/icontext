#!/usr/bin/env bash
# icontext installer
# Usage: curl -fsSL https://raw.githubusercontent.com/floomhq/icontext/main/get.sh | bash

set -euo pipefail

ICONTEXT_DIR="${ICONTEXT_DIR:-$HOME/icontext}"
BIN_DIR="$HOME/.local/bin"

echo "icontext: installing..."

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
    echo "icontext: missing required tools: ${MISSING_DEPS[*]}"
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
    echo "Then re-run: curl -fsSL https://icontext.floom.dev/install | bash"
    exit 1
fi
# -----------------------------------------------------------------------------

# Clone or update
if [ -d "$ICONTEXT_DIR/.git" ]; then
    echo "icontext: updating $ICONTEXT_DIR"
    git -C "$ICONTEXT_DIR" pull --ff-only --quiet
else
    echo "icontext: cloning to $ICONTEXT_DIR"
    git clone --quiet https://github.com/floomhq/icontext "$ICONTEXT_DIR"
fi

# Install CLI
# Note: in agents mode, install.sh creates a symlink from ~/.local/bin/icontext
# into the vault AFTER the vault is created by `icontext init`. We install a
# direct symlink to the repo here so the CLI is available immediately.
mkdir -p "$BIN_DIR"
if command -v pip3 &>/dev/null && pip3 install -e "$ICONTEXT_DIR" --quiet 2>/dev/null; then
    echo "icontext: CLI installed via pip"
else
    ln -sf "$ICONTEXT_DIR/cli.py" "$BIN_DIR/icontext"
    chmod +x "$ICONTEXT_DIR/cli.py"
    echo "icontext: CLI linked to $BIN_DIR/icontext"
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
        echo '# icontext' >> "$SHELL_RC"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        echo "icontext: added ~/.local/bin to PATH in $SHELL_RC"
    fi
fi

echo ""
echo "icontext: done."
echo ""
echo "  Next:"
echo "    1. Restart your terminal (or: source ~/.zshrc)"
echo "    2. Run: icontext init"
echo "    3. Open Claude Code and say: \"populate my icontext profile\""
echo ""
echo "  No API keys needed. Your agent does the synthesis."
