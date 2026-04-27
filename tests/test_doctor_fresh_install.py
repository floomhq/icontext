import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.doctor import FreshInstallDoctor


SCRIPT_NAMES = [
    "icontext_classify.py",
    "check_tiers.py",
    "indexlib.py",
    "update_index.py",
    "prompt_context.py",
    "install_claude_integration.py",
    "doctor.py",
    "eval_retrieval.py",
]


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o755)


def make_icontext_root(tmp_path: Path) -> Path:
    root = tmp_path / "icontext"
    for directory in ["config", "workflows", "mcp", "scripts", "hooks"]:
        (root / directory).mkdir(parents=True)
    (root / "config" / "gitleaks.toml").write_text("title = 'test'\n", encoding="utf-8")
    (root / "config" / "tiers.yml").write_text("tiers: []\n", encoding="utf-8")
    (root / "workflows" / "sensitivity.yml").write_text("name: test\n", encoding="utf-8")
    (root / "mcp" / "server.py").write_text("# test\n", encoding="utf-8")
    for hook in FreshInstallDoctor.HOOKS:
        write_executable(root / "hooks" / hook, "#!/usr/bin/env bash\nexit 0\n")
    for script in SCRIPT_NAMES:
        write_executable(root / "scripts" / script, "#!/usr/bin/env python3\n")

    write_executable(
        root / "install.sh",
        r"""#!/usr/bin/env bash
set -euo pipefail
dry_run=0
yes=0
mode=standard
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run=1 ;;
    --yes) yes=1 ;;
    --mode) mode="$2"; shift ;;
    *) echo "unexpected arg: $1"; exit 2 ;;
  esac
  shift
done
if [ "$yes" -ne 1 ]; then
  echo "--yes required"
  exit 2
fi
if [ "$dry_run" -eq 1 ]; then
  exit 0
fi
export MODE="$mode"
python3 - <<'PY'
import hashlib
import json
import os
import shutil
from pathlib import Path

root = Path(os.environ["ICONTEXT_ROOT"])
vault = Path(os.environ["VAULT"])
for hook in ["pre-commit", "pre-push", "post-commit"]:
    dst = vault / ".git" / "hooks" / hook
    dst.write_text("hook\n", encoding="utf-8")
for src, dst in [
    (root / "config" / "gitleaks.toml", vault / ".gitleaks.toml"),
    (root / "config" / "tiers.yml", vault / ".icontext-tiers.yml"),
    (root / "workflows" / "sensitivity.yml", vault / ".github/workflows/icontext-sensitivity.yml"),
    (root / "mcp" / "server.py", vault / ".icontext/mcp/server.py"),
]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
(vault / ".icontext/scripts").mkdir(parents=True, exist_ok=True)
for src in sorted((root / "scripts").glob("*.py")):
    shutil.copyfile(src, vault / ".icontext/scripts" / src.name)
(vault / ".icontext-installed").write_text("installed\n", encoding="utf-8")
paths = [
    ".gitleaks.toml",
    ".icontext-tiers.yml",
    ".github/workflows/icontext-sensitivity.yml",
    ".icontext/mcp/server.py",
    ".icontext-installed",
]
paths.extend(f".icontext/scripts/{src.name}" for src in sorted((root / "scripts").glob("*.py")))
manifest = {"files": {}}
for rel in paths:
    manifest["files"][rel] = {"sha256": hashlib.sha256((vault / rel).read_bytes()).hexdigest()}
(vault / ".icontext").mkdir(exist_ok=True)
(vault / ".icontext/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
if os.environ.get("MODE", "") == "agents":
    home = Path(os.environ["HOME"])
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude/.mcp.json").write_text("{}\n", encoding="utf-8")
    (home / ".claude/settings.json").write_text("{}\n", encoding="utf-8")
    (home / ".codex").mkdir(parents=True, exist_ok=True)
    (home / ".codex/config.toml").write_text("", encoding="utf-8")
    (home / ".cursor").mkdir(parents=True, exist_ok=True)
    (home / ".cursor/mcp.json").write_text("{}\n", encoding="utf-8")
    (home / ".config/opencode").mkdir(parents=True, exist_ok=True)
    (home / ".config/opencode/opencode.json").write_text("{}\n", encoding="utf-8")
PY
""",
    )
    write_executable(
        root / "uninstall.sh",
        r"""#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" != "--yes" ]; then
  echo "--yes required"
  exit 2
fi
python3 - <<'PY'
import os
import shutil
from pathlib import Path

vault = Path(os.environ["VAULT"])
for hook in ["pre-commit", "pre-push", "post-commit"]:
    (vault / ".git" / "hooks" / hook).unlink(missing_ok=True)
for rel in [".gitleaks.toml", ".icontext-tiers.yml", ".icontext-installed", ".github/workflows/icontext-sensitivity.yml"]:
    (vault / rel).unlink(missing_ok=True)
shutil.rmtree(vault / ".icontext", ignore_errors=True)
PY
""",
    )
    return root


class FreshInstallDoctorTests(unittest.TestCase):
    def test_fresh_install_verifies_install_manifest_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            icontext_root = make_icontext_root(Path(tmp))

            doctor = FreshInstallDoctor(icontext_root)
            self.assertEqual(doctor.run(), 0)
            statuses = {check.name: check.status for check in doctor.checks}
            self.assertEqual(statuses["fresh-install:dry-run:no-mutations"], "pass")
            self.assertEqual(statuses["fresh-install:manifest"], "pass")
            self.assertEqual(statuses["fresh-install:uninstall:removed"], "pass")
            self.assertEqual(statuses["fresh-install:uninstall:repo"], "pass")
            self.assertTrue(all(check.status == "pass" for check in doctor.checks))


if __name__ == "__main__":
    unittest.main()
