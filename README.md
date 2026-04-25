# icontext

Tooling for personal context vaults: secret scanning, sensitivity classification, semantic search, and MCP access. Install into any git repo used as a private knowledge vault.

## What it does today

1. **Pre-commit** blocks commits containing API keys, tokens, or PII (via gitleaks).
2. **Pre-push** classifies each changed file with deterministic rules and blocks pushes where file content's sensitivity exceeds its folder's tier.
3. **GitHub Actions** re-runs the classifier on every push for an audit trail.
4. **Post-commit** preserves Git LFS behavior and records a local index marker.

## Planned

- Semantic index of vault contents.
- MCP server exposing `search_vault`, `read_vault_file`, and `append_log`.

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

This symlinks hooks, installs the GitHub Actions workflow, copies runtime scripts into `.icontext/scripts/`, and writes `config/tiers.yml` into the vault root.

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

## Status

Early. Built for Federico's `federicodeponte/context`. Generic enough to install elsewhere.
