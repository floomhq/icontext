#!/usr/bin/env python3
"""Minimal stdio MCP server for icontext."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from indexlib import append_log, read_text, rebuild, search


def _content(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _tools() -> list[dict]:
    return [
        {
            "name": "search_vault",
            "description": "Search the local icontext index.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                    "tier": {"type": "string", "enum": ["shareable", "internal", "vault"]},
                },
                "required": ["query"],
            },
        },
        {
            "name": "read_vault_file",
            "description": "Read a text file from the local context vault.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 50000, "default": 12000},
                },
                "required": ["path"],
            },
        },
        {
            "name": "append_log",
            "description": "Append a timestamped note to a context log file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "vault/secretary/logs/icontext.md"},
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
        },
        {
            "name": "rebuild_index",
            "description": "Rebuild the local icontext search index.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


class Server:
    def __init__(self, repo: Path):
        self.repo = repo

    def handle(self, method: str, params: dict | None) -> dict | None:
        params = params or {}
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "icontext", "version": "0.1.0"},
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return {"tools": _tools()}
        if method == "tools/call":
            return self.call_tool(params)
        raise ValueError(f"unsupported method: {method}")

    def call_tool(self, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "search_vault":
            results = search(
                self.repo,
                str(args["query"]),
                limit=int(args.get("limit", 5)),
                tier=args.get("tier"),
            )
            return _content(
                json.dumps(
                    [
                        {
                            "path": result.path,
                            "tier": result.tier,
                            "score": result.score,
                            "snippet": result.snippet,
                        }
                        for result in results
                    ],
                    indent=2,
                )
            )
        if name == "read_vault_file":
            text = read_text(self.repo, str(args["path"]), int(args.get("max_chars", 12000)))
            return _content(text)
        if name == "append_log":
            path = str(args.get("path") or "vault/secretary/logs/icontext.md")
            stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            append_log(self.repo, path, f"- [{stamp}] {args['text']}")
            rebuild(self.repo)
            return _content(f"appended to {path}")
        if name == "rebuild_index":
            indexed = rebuild(self.repo)
            return _content(f"indexed {indexed} text file(s)")
        raise ValueError(f"unknown tool: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/Users/federicodeponte/context")
    args = parser.parse_args()
    server = Server(Path(args.repo).expanduser().resolve())

    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        request_id = request.get("id")
        try:
            result = server.handle(request.get("method", ""), request.get("params"))
            if request_id is None:
                continue
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            if request_id is None:
                continue
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(exc)},
            }
        print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
