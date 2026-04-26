# icontext

[![CI](https://github.com/buildingopen/icontext/actions/workflows/ci.yml/badge.svg)](https://github.com/buildingopen/icontext/actions/workflows/ci.yml)

**Encrypted AI context vault for Claude Code, Codex, Cursor, and OpenCode.**

Turn a private context repo into agent-ready infrastructure: encrypted Git
tiers, gitleaks, deterministic sensitivity checks, local SQLite retrieval, MCP
tools, Claude prompt context, multi-agent config, and one doctor command that
proves the whole system works.

`icontext` is for people who want AI agents to use their real operating context
without turning private notes, legal files, tax records, credentials, emails,
PDFs, and strategy docs into prompt soup.

## What You Get

```text
your-context-repo/
  shareable/       public-safe notes and assets
  internal/        private working context
  vault/           git-crypt encrypted legal, identity, admin, secrets, PDFs
  .icontext/       local runtime copied in by the installer
```

Then your agents get the same local context layer:

```text
Claude Code  -> prompt hook + MCP
Codex        -> MCP
Cursor       -> MCP
OpenCode     -> MCP
GitHub       -> gitleaks + tier CI
```

## Why

AI agents are only as useful as the context they can safely access. Most private
operating context lives in messy folders, old notes, legal files, emails,
credentials, PDFs, and strategy docs. That context is too sensitive to paste
into prompts and too important to leave invisible.

`icontext` turns a private context repo into infrastructure:

- **encrypted in Git** where it needs to be encrypted
- **guarded before commit, push, and CI** before secrets leak
- **searchable locally** without hosted vector databases
- **available to Claude Code, Codex, Cursor, and OpenCode** through one MCP server
- **verified end to end** by one `doctor.py` command

## Features

| Layer | What icontext does |
|---|---|
| Encryption | `vault/**` is protected with `git-crypt` in Git and on GitHub. |
| Secret scanning | `gitleaks` runs locally and in GitHub Actions. |
| Tier enforcement | deterministic classifier blocks sensitive files in lower-trust folders. |
| Retrieval | local SQLite FTS index, rebuilt by hook, no API key required. |
| MCP | `search_vault`, `read_vault_file`, `append_log`, `rebuild_index`. |
| Claude Code | `UserPromptSubmit` hook with conservative tier and character limits. |
| Codex, Cursor, OpenCode | installer writes the matching MCP config for each agent. |
| Verification | `doctor.py --deep` checks hooks, encryption, index, MCP, agents, gitleaks, and CI. |
| Evaluation | `eval_retrieval.py` tests whether important prompts hit expected files. |

## Planned

- Optional embedding reranker for semantic ranking beyond FTS.

## Tiers

A vault split into three top-level folders:

| Folder | Meaning | Encryption |
|---|---|---|
| `shareable/` | Could be published without harm | Plaintext |
| `internal/` | Personal/business but not catastrophic if leaked | Plaintext |
| `vault/` | Must never leak | git-crypt encrypted |

The classifier enforces content matches folder. Secrets are never allowed anywhere without git-crypt.

## Install

```bash
git clone https://github.com/buildingopen/icontext ~/icontext
cd /path/to/your/context-repo
bash ~/icontext/install.sh
```

This symlinks hooks, installs the GitHub Actions workflow, copies runtime scripts into `.icontext/scripts/`, installs the MCP server into `.icontext/mcp/`, and writes `config/tiers.yml` into the vault root.

## Agent Integrations

```bash
python3 .icontext/scripts/update_index.py --repo .
python3 .icontext/scripts/install_claude_integration.py --icontext-root ~/icontext --repo .
```

This updates:

- `~/.claude/.mcp.json` with an `icontext` MCP server and `~/.claude/settings.json` with a `UserPromptSubmit` hook.
- `~/.codex/config.toml` with `[mcp_servers.icontext]`.
- `~/.cursor/mcp.json` with `mcpServers.icontext`.
- `~/.config/opencode/opencode.json` with `mcp.icontext`.

The Claude prompt hook defaults to `ICONTEXT_MAX_TIER=internal`, which means
passive prompt injection excludes `vault/` snippets unless you explicitly opt in
with `ICONTEXT_MAX_TIER=vault`. Explicit MCP tool calls can still search or read
vault files.

## Prove It Works

```bash
python3 .icontext/scripts/doctor.py --repo . --icontext-root ~/icontext --deep
```

The doctor command is the quality gate for Federico's setup. It validates the
current install without starting background services or adding hosted
dependencies.

Example production result:

```text
summary: 27 pass, 0 warn, 0 fail
```

## Retrieval Eval

```bash
python3 .icontext/scripts/eval_retrieval.py --repo . --cases .icontext/retrieval-eval.json
```

The eval file is intentionally local to each vault. `icontext` provides the
runner; your repo owns the prompts and expected files that matter.

## Uninstall

```bash
bash ~/icontext/uninstall.sh /path/to/vault
```

## Requirements

- `gitleaks` (`brew install gitleaks`)
- `git-crypt` (`brew install git-crypt`)
- `git-lfs` (`brew install git-lfs`)
- Python 3.11+
- No API key is required for the deterministic tier classifier.

## Launch Status

`icontext` is production-proven in Federico's private `context` vault:

- `doctor.py`: 27 pass, 0 warnings, 0 failures
- retrieval eval: 3 pass, 0 failures
- all tracked `vault/**` files encrypted in `HEAD`
- current-tree and full-history gitleaks scans clean after history rewrite
- Claude Code, Codex, Cursor, and OpenCode wiring verified

## What icontext Is Not

- not a hosted vector database
- not a replacement for Obsidian, Notion, or a full PKM system
- not an agent framework
- not a way to make leaked git-crypt keys safe
- not magic semantic search; current retrieval is SQLite FTS by design

## Keywords

AI context vault, encrypted context repository, Claude Code MCP, Codex MCP,
Cursor MCP, OpenCode MCP, git-crypt vault, gitleaks pre-commit, context
engineering, personal knowledge management, local-first AI agents, SQLite FTS
retrieval.

## Status

Built for Federico's `federicodeponte/context` and kept generic enough to
install into another private Git knowledge vault.
