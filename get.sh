#!/usr/bin/env bash
# icontext installer
# Usage: curl -fsSL https://raw.githubusercontent.com/floomhq/icontext/main/get.sh | bash

set -euo pipefail

ICONTEXT_DIR="${ICONTEXT_DIR:-$HOME/icontext}"
BIN_DIR="$HOME/.local/bin"

echo "icontext: installing..."

# Clone or update
if [ -d "$ICONTEXT_DIR/.git" ]; then
    echo "icontext: updating $ICONTEXT_DIR"
    git -C "$ICONTEXT_DIR" pull --ff-only --quiet
else
    echo "icontext: cloning to $ICONTEXT_DIR"
    git clone --quiet https://github.com/floomhq/icontext "$ICONTEXT_DIR"
fi

# Install CLI
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
echo "icontext: restart your terminal, then run: icontext init"
