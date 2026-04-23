# icontext

Tooling for personal context vaults: secret scanning, sensitivity classification, semantic search, and MCP access. Install into any git repo used as a private knowledge vault.

## What it does

1. **Pre-commit** blocks commits containing API keys, tokens, or PII (via gitleaks).
2. **Pre-push** classifies each changed file with an LLM and blocks pushes where file content's sensitivity exceeds its folder's tier.
3. **GitHub Actions** re-runs the classifier on every push for an audit trail.
4. **Post-commit** updates a local semantic index of vault contents.
5. **MCP server** exposes `search_vault`, `read_vault_file`, and `append_log` tools to Claude from any session.

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

This symlinks hooks, installs the GitHub Actions workflow, and writes `config/tiers.yml` into the vault root.

## Uninstall

```bash
bash ~/icontext/uninstall.sh /path/to/vault
```

## Requirements

- `gitleaks` (brew install gitleaks)
- `git-crypt` (brew install git-crypt)
- `git-lfs` (brew install git-lfs)
- Python 3.11+
- A Gemini or Claude API key (env: `GEMINI_API_KEY` or `ANTHROPIC_API_KEY`)

## Status

Early. Built for Federico's `federicodeponte/context`. Generic enough to install elsewhere.
