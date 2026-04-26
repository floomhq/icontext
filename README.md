# icontext: encrypted AI context vault for Claude Code, Codex, Cursor, and OpenCode

Local-first tooling for an encrypted AI context vault: secret scanning,
sensitivity tiers, git-crypt protection, SQLite full-text retrieval, MCP access,
and agent integrations for Claude Code, Codex, Cursor, and OpenCode.

Use `icontext` when your personal or company context repository needs to be
useful to AI coding agents without leaking private notes, legal files, tax
records, credentials, emails, PDFs, or strategy docs.

## What it does today

1. **Pre-commit** blocks commits containing API keys, tokens, or PII (via gitleaks).
2. **Pre-push** classifies each changed file with deterministic rules and blocks pushes where file content's sensitivity exceeds its folder's tier.
3. **GitHub Actions** re-runs the classifier on every push for an audit trail.
4. **Post-commit** preserves Git LFS behavior and updates a local SQLite FTS index.
5. **MCP server** exposes `search_vault`, `read_vault_file`, `append_log`, and `rebuild_index`.
6. **Agent integrations** wire the same vault MCP server into Claude Code, Codex, Cursor, and OpenCode. Claude Code also gets a `UserPromptSubmit` hook.
7. **Doctor check** verifies hooks, encryption, index, MCP, agent config, native client registration, gitleaks, and GitHub Actions.
8. **Retrieval eval** measures whether important prompts retrieve the expected vault files.

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
cd /path/to/your/vault
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

## Verify

```bash
python3 .icontext/scripts/doctor.py --repo . --icontext-root ~/icontext --deep
```

The doctor command is the quality gate for Federico's setup. It validates the
current install without starting background services or adding hosted
dependencies.

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

- `gitleaks` (brew install gitleaks)
- `git-crypt` (brew install git-crypt)
- `git-lfs` (brew install git-lfs)
- Python 3.11+
- No API key is required for the deterministic tier classifier.

## Keywords

AI context vault, encrypted context repository, Claude Code MCP, Codex MCP,
Cursor MCP, OpenCode MCP, git-crypt vault, gitleaks pre-commit, context
engineering, personal knowledge management, local-first AI agents, SQLite FTS
retrieval.

## Status

Built for Federico's `federicodeponte/context` and kept generic enough to
install into another private Git knowledge vault.
