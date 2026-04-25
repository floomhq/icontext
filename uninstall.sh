#!/usr/bin/env bash
# icontext uninstaller: remove hooks, configs, and workflow from a vault.
#
# Usage: bash ~/icontext/uninstall.sh [/path/to/vault]

set -euo pipefail

VAULT="${1:-$PWD}"

if [ ! -d "$VAULT/.git" ]; then
    echo "icontext: $VAULT is not a git repo"
    exit 1
fi

echo "icontext: uninstalling from $VAULT"

for hook in pre-commit pre-push post-commit; do
    f="$VAULT/.git/hooks/$hook"
    if [ -L "$f" ]; then
        rm "$f"
        echo "  - removed hook $hook"
    fi
done

for f in .gitleaks.toml .icontext-tiers.yml .icontext-installed; do
    if [ -f "$VAULT/$f" ]; then
        rm "$VAULT/$f"
        echo "  - removed $f"
    fi
done

if [ -d "$VAULT/.icontext" ]; then
    rm -rf "$VAULT/.icontext"
    echo "  - removed .icontext"
fi

if [ -f "$VAULT/.github/workflows/icontext-sensitivity.yml" ]; then
    rm "$VAULT/.github/workflows/icontext-sensitivity.yml"
    echo "  - removed .github/workflows/icontext-sensitivity.yml"
fi

echo "icontext: uninstall complete"
