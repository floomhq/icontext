#!/usr/bin/env bash
# fbrain uninstaller: remove files recorded in .icontext/manifest.json.

set -euo pipefail

VAULT="$PWD"
YES=0
DRY_RUN=0

usage() {
    cat <<EOF
Usage: bash uninstall.sh [options] [vault-path]

Options:
  --vault PATH       target context repo (default: current directory)
  --dry-run          print removals without deleting files
  --yes              skip interactive confirmation
  -h, --help         show this help
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --vault)
            VAULT="${2:-}"
            [ -n "$VAULT" ] || { echo "fbrain: --vault requires a path"; exit 1; }
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
        -*)
            echo "fbrain: unknown option: $1"
            usage
            exit 1
            ;;
        *)
            VAULT="$1"
            shift
            ;;
    esac
done

VAULT="$(cd "$VAULT" && pwd)"

if [ ! -d "$VAULT/.git" ]; then
    echo "fbrain: $VAULT is not a git repo"
    exit 1
fi

MANIFEST="$VAULT/.icontext/manifest.json"

echo "fbrain: uninstall plan"
echo "  target: $VAULT"
if [ "$DRY_RUN" -eq 1 ]; then
    echo "  dry-run: yes"
fi

if [ ! -f "$MANIFEST" ]; then
    echo "fbrain: manifest missing; refusing manifest-aware uninstall"
    echo "fbrain: remove legacy installs manually or reinstall fbrain to create a manifest"
    exit 1
fi

run_uninstall_plan() {
    local dry="$1"
    python3 - "$MANIFEST" "$dry" <<'PY'
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
dry_run = sys.argv[2] == "1"
data = json.loads(manifest.read_text(encoding="utf-8"))
vault = manifest.parent.parent

def sha256(path: Path) -> str | None:
    if not path.exists() or path.is_symlink():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def remove_path(path: Path) -> None:
    if dry_run:
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()

for entry in data.get("files", []):
    rel = entry.get("relative_path")
    if isinstance(rel, str) and rel:
        path = vault / rel
    else:
        path = Path(entry["path"])
    kind = entry.get("kind")
    label = entry.get("relative_path", path)
    if not path.exists() and not path.is_symlink():
        print(f"  - already absent {label}")
        continue

    if kind == "symlink":
        expected = entry.get("source")
        if not path.is_symlink():
            print(f"  ! skip modified non-symlink {label}")
            continue
        if expected and str(path.resolve()) != expected:
            print(f"  ! skip changed symlink {label}")
            continue
        print(f"  - remove {label}")
        remove_path(path)
        continue

    expected_hash = entry.get("sha256")
    current_hash = sha256(path)
    if expected_hash and current_hash and current_hash != expected_hash:
        print(f"  ! skip modified file {label}")
        continue

    print(f"  - remove {label}")
    remove_path(path)

if manifest.exists():
    print("  - remove .icontext/manifest.json")
    if not dry_run:
        manifest.unlink()

if not dry_run:
    for rel in [".icontext/mcp", ".icontext/scripts", ".icontext", ".github/workflows"]:
        path = vault / rel
        try:
            path.rmdir()
        except OSError:
            pass
PY
}

if [ "$DRY_RUN" -eq 1 ]; then
    run_uninstall_plan 1
    echo "fbrain: dry run complete; no files were removed"
    exit 0
fi

if [ "$YES" -eq 0 ]; then
    if [ ! -t 0 ]; then
        echo ""
        echo "fbrain: refusing to uninstall non-interactively without --yes"
        exit 1
    fi
    echo ""
    printf "Proceed with these removals? [y/N] "
    read -r answer
    case "$answer" in
        y|Y|yes|YES) ;;
        *)
            echo "fbrain: cancelled"
            exit 1
        ;;
    esac
fi

run_uninstall_plan 0

echo "fbrain: uninstall complete"
