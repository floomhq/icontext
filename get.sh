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

# PATH check
if ! echo "$PATH" | grep -q "$BIN_DIR"; then
    echo ""
    echo "icontext: add to your shell profile if needed:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "icontext: done. Run:"
echo "  icontext init"
