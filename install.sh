#!/usr/bin/env bash
# icontext installer: wires hooks, configs, and workflows into a vault repo.
#
# Usage:
#   cd /path/to/vault && bash ~/icontext/install.sh
#
# Idempotent. Re-running updates symlinks to latest icontext state.

set -euo pipefail

ICONTEXT_ROOT="${ICONTEXT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
VAULT="${VAULT:-$PWD}"

if [ ! -d "$VAULT/.git" ]; then
    echo "icontext: $VAULT is not a git repo. cd into the vault first."
    exit 1
fi

echo "icontext: installing into $VAULT"
echo "icontext: source is $ICONTEXT_ROOT"

# 1. Hooks
mkdir -p "$VAULT/.git/hooks"
for hook in pre-commit pre-push post-commit; do
    src="$ICONTEXT_ROOT/hooks/$hook"
    dst="$VAULT/.git/hooks/$hook"
    if [ -f "$src" ]; then
        chmod +x "$src"
        ln -sf "$src" "$dst"
        echo "  + hook $hook -> $src"
    fi
done

# 2. Config: gitleaks.toml at vault root (git-tracked so team members pick it up)
if [ -f "$ICONTEXT_ROOT/config/gitleaks.toml" ]; then
    cp "$ICONTEXT_ROOT/config/gitleaks.toml" "$VAULT/.gitleaks.toml"
    echo "  + .gitleaks.toml copied into vault root"
fi

# 3. Tiers config (used by classifier + install awareness)
if [ -f "$ICONTEXT_ROOT/config/tiers.yml" ]; then
    cp "$ICONTEXT_ROOT/config/tiers.yml" "$VAULT/.icontext-tiers.yml"
    echo "  + .icontext-tiers.yml copied into vault root"
fi

# 4. GitHub Actions workflow (only if .github/workflows dir exists or can be created)
if [ -f "$ICONTEXT_ROOT/workflows/sensitivity.yml" ]; then
    mkdir -p "$VAULT/.github/workflows"
    cp "$ICONTEXT_ROOT/workflows/sensitivity.yml" "$VAULT/.github/workflows/icontext-sensitivity.yml"
    echo "  + .github/workflows/icontext-sensitivity.yml installed"
fi

# 5. Record install marker
cat > "$VAULT/.icontext-installed" <<EOF
# icontext install marker
icontext_root=$ICONTEXT_ROOT
installed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
echo "  + .icontext-installed marker written"

echo ""
echo "icontext: install complete"
echo ""
echo "Next steps:"
echo "  1. Review .gitleaks.toml and .icontext-tiers.yml in vault root, commit them"
echo "  2. Test pre-commit: echo 'AKIA_FAKE_TEST=abc123' > /tmp/leak-test.md && cp /tmp/leak-test.md . && git add leak-test.md && git commit -m 'test'"
echo "  3. (Phase 4+) Set GEMINI_API_KEY in env for sensitivity classifier"
