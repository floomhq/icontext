#!/usr/bin/env bash
# icontext installer: wires hooks, configs, workflows, and local runtime into a vault repo.

set -euo pipefail

ICONTEXT_ROOT="${ICONTEXT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
VAULT="${VAULT:-$PWD}"
MODE="standard"
DRY_RUN=0
YES=0
DO_WRITE=0

usage() {
    cat <<EOF
Usage: bash install.sh [options]

Run from the target context repo, or pass --vault PATH.

Options:
  --vault PATH       target context repo (default: current directory)
  --mode MODE        minimal, standard, or agents (default: standard)
  --dry-run          print planned changes without writing files
  --yes              skip interactive confirmation
  -h, --help         show this help

Modes:
  minimal            copy config, runtime scripts, and MCP server; no hooks or CI
  standard           minimal + git hooks + GitHub Actions workflow
  agents             standard + Claude/Codex/Cursor/OpenCode MCP config wiring
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --vault)
            VAULT="${2:-}"
            [ -n "$VAULT" ] || { echo "icontext: --vault requires a path"; exit 1; }
            shift 2
            ;;
        --mode)
            MODE="${2:-}"
            [ -n "$MODE" ] || { echo "icontext: --mode requires minimal, standard, or agents"; exit 1; }
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --yes)
            YES=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "icontext: unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

case "$MODE" in
    minimal|standard|agents) ;;
    *)
        echo "icontext: invalid mode '$MODE' (expected minimal, standard, or agents)"
        exit 1
        ;;
esac

VAULT="$(cd "$VAULT" && pwd)"

if [ ! -d "$VAULT/.git" ]; then
    echo "icontext: $VAULT is not a git repo. cd into the vault first."
    exit 1
fi

declare -a MANIFEST_LINES=()

add_manifest_entry() {
    local path="$1"
    local source="$2"
    local kind="$3"
    MANIFEST_LINES+=("$path"$'\t'"$source"$'\t'"$kind")
}

plan() {
    echo "  $1"
}

copy_file() {
    local src="$1"
    local dst="$2"
    local label="$3"
    local executable="${4:-0}"
    [ -f "$src" ] || return 0
    plan "+ $label"
    add_manifest_entry "$dst" "$src" "file"
    if [ "$DO_WRITE" -eq 1 ]; then
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        if [ "$executable" = "1" ]; then
            chmod +x "$dst"
        fi
    fi
}

write_symlink() {
    local src="$1"
    local dst="$2"
    local label="$3"
    [ -f "$src" ] || return 0
    plan "+ $label -> $src"
    add_manifest_entry "$dst" "$src" "symlink"
    if [ "$DO_WRITE" -eq 1 ]; then
        mkdir -p "$(dirname "$dst")"
        chmod +x "$src"
        ln -sf "$src" "$dst"
    fi
}

write_marker() {
    local dst="$VAULT/.icontext-installed"
    plan "+ .icontext-installed marker"
    add_manifest_entry "$dst" "" "generated"
    if [ "$DO_WRITE" -eq 1 ]; then
        cat > "$dst" <<EOF
# icontext install marker
icontext_root=$ICONTEXT_ROOT
installed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mode=$MODE
EOF
    fi
}

write_manifest() {
    local manifest="$VAULT/.icontext/manifest.json"
    local temp
    temp="$(mktemp)"
    for line in "${MANIFEST_LINES[@]}"; do
        printf '%s\n' "$line" >> "$temp"
    done
    python3 - "$temp" "$manifest" "$ICONTEXT_ROOT" "$VAULT" "$MODE" <<'PY'
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

lines = Path(sys.argv[1])
manifest = Path(sys.argv[2])
icontext_root = Path(sys.argv[3])
vault = Path(sys.argv[4])
mode = sys.argv[5]

def sha256(path: Path) -> str | None:
    if not path.exists() or path.is_symlink():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def git_commit(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except Exception:
        return None

entries = []
for raw in lines.read_text(encoding="utf-8").splitlines():
    path_s, source_s, kind = raw.split("\t", 2)
    path = Path(path_s)
    source = Path(source_s) if source_s else None
    entry = {
        "path": str(path),
        "relative_path": str(path.relative_to(vault)) if path.is_relative_to(vault) else str(path),
        "kind": kind,
        "source": str(source) if source else None,
        "sha256": sha256(path),
        "source_sha256": sha256(source) if source else None,
    }
    if path.is_symlink():
        entry["link_target"] = str(path.resolve())
    entries.append(entry)

payload = {
    "schema": 1,
    "tool": "icontext",
    "mode": mode,
    "icontext_root": str(icontext_root),
    "vault": str(vault),
    "icontext_commit": git_commit(icontext_root),
    "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "files": entries,
}
manifest.parent.mkdir(parents=True, exist_ok=True)
manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
    rm -f "$temp"
    plan "+ .icontext/manifest.json"
}

echo "icontext: install plan"
echo "  target: $VAULT"
echo "  source: $ICONTEXT_ROOT"
echo "  mode:   $MODE"
if [ "$DRY_RUN" -eq 1 ]; then
    echo "  dry-run: yes"
fi

echo ""
echo "What this installer changes:"

install_actions() {
    copy_file "$ICONTEXT_ROOT/config/gitleaks.toml" "$VAULT/.gitleaks.toml" ".gitleaks.toml"
    copy_file "$ICONTEXT_ROOT/config/tiers.yml" "$VAULT/.icontext-tiers.yml" ".icontext-tiers.yml"
    for script in icontext_classify.py check_tiers.py indexlib.py update_index.py prompt_context.py install_claude_integration.py doctor.py eval_retrieval.py; do
        copy_file "$ICONTEXT_ROOT/scripts/$script" "$VAULT/.icontext/scripts/$script" ".icontext/scripts/$script" 1
    done
    copy_file "$ICONTEXT_ROOT/mcp/server.py" "$VAULT/.icontext/mcp/server.py" ".icontext/mcp/server.py" 1

    if [ "$MODE" = "standard" ] || [ "$MODE" = "agents" ]; then
        for hook in pre-commit pre-push post-commit; do
            write_symlink "$ICONTEXT_ROOT/hooks/$hook" "$VAULT/.git/hooks/$hook" ".git/hooks/$hook"
        done
        copy_file "$ICONTEXT_ROOT/workflows/sensitivity.yml" "$VAULT/.github/workflows/icontext-sensitivity.yml" ".github/workflows/icontext-sensitivity.yml"
    fi

    write_marker
    if [ "$DO_WRITE" -eq 1 ]; then
        write_manifest
    else
        plan "+ .icontext/manifest.json"
    fi
}

install_actions

if [ "$DRY_RUN" -eq 1 ]; then
    echo ""
    echo "icontext: dry run complete; no files were changed"
    exit 0
fi

if [ "$YES" -eq 0 ]; then
    if [ ! -t 0 ]; then
        echo ""
        echo "icontext: refusing to install non-interactively without --yes"
        exit 1
    fi
    echo ""
    printf "Proceed with these changes? [y/N] "
    read -r answer
    case "$answer" in
        y|Y|yes|YES) ;;
        *)
            echo "icontext: cancelled"
            exit 1
            ;;
    esac
fi

MANIFEST_LINES=()
DO_WRITE=1
echo ""
echo "icontext: applying changes"
install_actions

if [ "$MODE" = "agents" ]; then
    echo "icontext: installing agent integrations"
    python3 "$VAULT/.icontext/scripts/install_claude_integration.py" --icontext-root "$ICONTEXT_ROOT" --repo "$VAULT"
fi

echo ""
echo "icontext: install complete"
echo ""
echo "Next steps:"
echo "  1. Review .gitleaks.toml, .icontext-tiers.yml, .icontext/scripts, and .icontext/manifest.json"
echo "  2. Build local search index: python3 .icontext/scripts/update_index.py --repo ."
if [ "$MODE" != "agents" ]; then
    echo "  3. Optional agent integrations: python3 .icontext/scripts/install_claude_integration.py --icontext-root $ICONTEXT_ROOT --repo $VAULT"
    echo "  4. Verify everything: python3 .icontext/scripts/doctor.py --repo . --icontext-root $ICONTEXT_ROOT --deep"
else
    echo "  3. Verify everything: python3 .icontext/scripts/doctor.py --repo . --icontext-root $ICONTEXT_ROOT --deep"
fi
