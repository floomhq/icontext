#!/usr/bin/env python3
"""Local SQLite FTS index for icontext vaults."""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path


TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

MAX_INDEX_BYTES = 500_000
MAX_READ_BYTES = 2_000_000
TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]{2,}")


@dataclass(frozen=True)
class SearchResult:
    path: str
    tier: str
    score: float
    snippet: str


def repo_root(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve()


def state_dir(repo: str | Path) -> Path:
    path = repo_root(repo) / ".git" / "icontext"
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path(repo: str | Path) -> Path:
    return state_dir(repo) / "index.sqlite"


def connect(repo: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(index_path(repo))
    conn.execute("pragma journal_mode=wal")
    conn.execute(
        "create table if not exists docs ("
        "path text primary key, tier text not null, size integer not null, "
        "mtime integer not null, body text not null)"
    )
    conn.execute(
        "create virtual table if not exists docs_fts using fts5("
        "path, tier, body, content='docs', content_rowid='rowid')"
    )
    return conn


def tracked_files(repo: str | Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root(repo),
        check=True,
        stdout=subprocess.PIPE,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def tier_for_path(path: str) -> str:
    first = path.split("/", 1)[0]
    if first in {"shareable", "internal", "vault"}:
        return first
    return "root"


def is_text_candidate(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return True
    return Path(path).name in {"AGENTS.md", "CLAUDE.md", "README.md"}


def read_text(repo: str | Path, rel_path: str, limit: int = MAX_READ_BYTES) -> str:
    root = repo_root(repo)
    candidate = (root / rel_path).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"path escapes repo: {rel_path}")
    if not candidate.is_file():
        raise FileNotFoundError(rel_path)
    data = candidate.read_bytes()[:limit]
    if b"\0" in data[:4096]:
        raise ValueError(f"binary file cannot be read as text: {rel_path}")
    return data.decode("utf-8", errors="ignore")


def rebuild(repo: str | Path) -> int:
    root = repo_root(repo)
    conn = connect(root)
    paths = tracked_files(root)
    indexed = 0

    with conn:
        conn.execute("delete from docs_fts")
        conn.execute("delete from docs")
        for rel_path in paths:
            if not is_text_candidate(rel_path):
                continue
            full_path = root / rel_path
            if not full_path.is_file():
                continue
            size = full_path.stat().st_size
            if size > MAX_INDEX_BYTES:
                continue
            try:
                body = read_text(root, rel_path, MAX_INDEX_BYTES)
            except (FileNotFoundError, ValueError):
                continue
            if not body.strip():
                continue
            cursor = conn.execute(
                "insert into docs(path, tier, size, mtime, body) values (?, ?, ?, ?, ?)",
                (
                    rel_path,
                    tier_for_path(rel_path),
                    size,
                    int(full_path.stat().st_mtime),
                    body,
                ),
            )
            rowid = cursor.lastrowid
            conn.execute(
                "insert into docs_fts(rowid, path, tier, body) values (?, ?, ?, ?)",
                (rowid, rel_path, tier_for_path(rel_path), body),
            )
            indexed += 1

    conn.close()
    (state_dir(root) / "last-indexed").write_text(f"{indexed}\n", encoding="utf-8")
    return indexed


def _fts_query(query: str) -> str:
    tokens = [token.replace('"', "") for token in TOKEN_RE.findall(query)]
    return " OR ".join(f'"{token}"' for token in tokens[:12])


def _snippet(body: str, query: str, max_chars: int = 260) -> str:
    lowered = body.lower()
    positions = [
        lowered.find(token.lower())
        for token in TOKEN_RE.findall(query)
        if lowered.find(token.lower()) >= 0
    ]
    start = max(0, min(positions) - 80) if positions else 0
    snippet = " ".join(body[start : start + max_chars].split())
    return snippet


def search(repo: str | Path, query: str, limit: int = 5, tier: str | None = None) -> list[SearchResult]:
    root = repo_root(repo)
    db = index_path(root)
    if not db.exists():
        rebuild(root)
    conn = connect(root)
    match = _fts_query(query)
    if not match:
        return []

    params: list[object] = [match]
    where = "docs_fts match ?"
    if tier:
        where += " and docs.tier = ?"
        params.append(tier)
    params.append(limit)

    rows = conn.execute(
        "select docs.path, docs.tier, bm25(docs_fts) as score, docs.body "
        "from docs_fts join docs on docs_fts.rowid = docs.rowid "
        f"where {where} order by score limit ?",
        params,
    ).fetchall()
    conn.close()
    return [
        SearchResult(path=row[0], tier=row[1], score=float(row[2]), snippet=_snippet(row[3], query))
        for row in rows
    ]


def append_log(repo: str | Path, rel_path: str, text: str) -> Path:
    root = repo_root(repo)
    candidate = (root / rel_path).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"path escapes repo: {rel_path}")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    with candidate.open("a", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")
    return candidate
