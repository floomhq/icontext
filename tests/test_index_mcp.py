import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "mcp"))

from indexlib import append_log, read_text, rebuild, search
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


if __name__ == "__main__":
    unittest.main()
