import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "mcp"))

from indexlib import append_log, read_text, rebuild, search
from install_claude_integration import install_claude, install_codex, install_cursor, install_opencode
from server import Server


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)


class IcontextIndexMcpTests(unittest.TestCase):
    def test_index_search_read_and_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            (root / "vault" / "strategy").mkdir(parents=True)
            (root / "vault" / "strategy" / "openpaper.md").write_text(
                "OpenPaper roadmap: citations and academic search.\n", encoding="utf-8"
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, stdout=subprocess.PIPE)

            indexed = rebuild(root)
            results = search(root, "academic citations", limit=3)
            text = read_text(root, "vault/strategy/openpaper.md")
            append_log(root, "vault/secretary/logs/icontext.md", "- test log")

        self.assertEqual(indexed, 1)
        self.assertEqual(results[0].path, "vault/strategy/openpaper.md")
        self.assertIn("OpenPaper roadmap", text)

    def test_mcp_tool_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            (root / "vault").mkdir()
            (root / "vault" / "note.md").write_text(
                "Rocketlist onboarding and investor notes.\n", encoding="utf-8"
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, stdout=subprocess.PIPE)
            rebuild(root)

            server = Server(root)
            tools = server.handle("tools/list", {})
            result = server.call_tool(
                {"name": "search_vault", "arguments": {"query": "Rocketlist investor"}}
            )
            payload = json.loads(result["content"][0]["text"])

        self.assertEqual(tools["tools"][0]["name"], "search_vault")
        self.assertEqual(payload[0]["path"], "vault/note.md")

    def test_search_max_tier_filters_vault_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            (root / "internal").mkdir()
            (root / "vault").mkdir()
            (root / "internal" / "note.md").write_text(
                "Roadmap for investor onboarding.\n", encoding="utf-8"
            )
            (root / "vault" / "secret.md").write_text(
                "Roadmap for investor onboarding with private bank details.\n", encoding="utf-8"
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, stdout=subprocess.PIPE)
            rebuild(root)

            results = search(root, "roadmap investor onboarding", max_tier="internal")

        self.assertTrue(results)
        self.assertNotIn("vault/secret.md", [result.path for result in results])


class IcontextIntegrationInstallTests(unittest.TestCase):
    def test_agent_configs_are_installed_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            icontext_root = root / "icontext"
            repo = root / "context"
            claude_dir = root / ".claude"
            codex_config = root / ".codex" / "config.toml"
            cursor_mcp = root / ".cursor" / "mcp.json"
            opencode_config = root / ".config" / "opencode" / "opencode.json"

            codex_config.parent.mkdir(parents=True)
            codex_config.write_text('[mcp_servers.fetch]\ncommand = "uvx"\nargs = ["mcp-server-fetch"]\n', encoding="utf-8")
            cursor_mcp.parent.mkdir(parents=True)
            cursor_mcp.write_text('{"mcpServers":{"fetch":{"command":"uvx","args":["mcp-server-fetch"],"env":{}}}}\n', encoding="utf-8")
            opencode_config.parent.mkdir(parents=True)
            opencode_config.write_text('{"mcp":{"fetch":{"type":"local","command":["uvx","mcp-server-fetch"],"enabled":true}}}\n', encoding="utf-8")

            for _ in range(2):
                install_claude(claude_dir, icontext_root, repo)
                install_codex(codex_config, icontext_root, repo)
                install_cursor(cursor_mcp, icontext_root, repo)
                install_opencode(opencode_config, icontext_root, repo)

            claude_mcp = json.loads((claude_dir / ".mcp.json").read_text(encoding="utf-8"))
            claude_settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
            codex = tomllib.loads(codex_config.read_text(encoding="utf-8"))
            cursor = json.loads(cursor_mcp.read_text(encoding="utf-8"))
            opencode = json.loads(opencode_config.read_text(encoding="utf-8"))

        self.assertEqual(claude_mcp["mcpServers"]["icontext"]["command"], "python3")
        self.assertEqual(len(claude_settings["hooks"]["UserPromptSubmit"]), 1)
        self.assertEqual(codex["mcp_servers"]["icontext"]["command"], "python3")
        self.assertEqual(cursor["mcpServers"]["icontext"]["args"][-1], str(repo))
        self.assertEqual(opencode["mcp"]["icontext"]["command"][0], "python3")


if __name__ == "__main__":
    unittest.main()
