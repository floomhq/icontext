# icontext competitive benchmark

Date: 2026-04-26

## Position

icontext is Federico's private context substrate: encrypted Git-backed tiers,
local retrieval, local agent wiring, and a doctor command that proves the setup
still works.

It is not trying to become a broad agent workflow suite, hosted integration
platform, Obsidian plugin, or vector database product.

## Compared systems

| Project | Verified public positioning | What to learn | What not to copy |
|---|---|---|---|
| `garrytan/gstack` | Claude Code workflow stack with specialist commands for planning, review, QA, release, browser, retro, and memory. | Opinionated workflows and explicit quality gates beat generic prompts. | Do not import a large slash-command factory into icontext; Federico already has skills and workflows. |
| `bitbonsai/mcpvault` | Universal MCP bridge for Obsidian vaults with many note operations and client config examples. | Broad MCP client compatibility and safe file access matter. | Do not optimize for Obsidian frontmatter, tags, or plugin UX unless Federico moves this vault to Obsidian. |
| `zilliztech/claude-context` | Semantic code search MCP for large codebases, backed by external vector infrastructure. | Retrieval quality matters for big corpora. | Do not require hosted vector DBs or API keys for a personal private vault baseline. |
| `mksglu/context-mode` | Context window optimization and session continuity with SQLite/FTS style event tracking. | Local SQLite and compaction-aware retrieval are the right direction. | Do not sandbox every tool call or add a session recorder until Federico has a repeated failure case. |
| `Houseofmvps/codesight` | AI config generator and MCP server for project context across many coding tools. | Multi-agent config generation is table stakes. | Do not generate broad boilerplate instructions; this repo already has curated instructions. |

## Design bar

1. Works locally first, with no hosted dependency required.
2. Protects private content in Git, not just at runtime.
3. Gives Claude Code, Codex, Cursor, and OpenCode the same context access path.
4. Has a single command that proves the install is healthy.
5. Keeps features below the threshold where maintenance becomes the product.

## Current gap list after benchmark

- Keep `doctor.py` as the main quality gate and run it before claiming the
  system is healthy.
- Add embeddings only after FTS retrieval misses are observed in real sessions.
- Add more write tools only after specific repeated workflows require them.
- Add gstack-style workflow commands outside icontext, not inside the vault
  substrate.
