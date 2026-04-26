# Security Policy

## Supported Versions

`main` is the supported branch.

## Reporting a Vulnerability

Do not open a public issue for suspected secret leakage, encryption bypasses, or
prompt-context exposure.

Use GitHub private vulnerability reporting when available, or contact the
maintainer directly with:

- affected version or commit
- reproduction steps
- expected impact
- any logs with secrets redacted

## Security Model

`icontext` protects a private Git-backed context vault with layered controls:

- `gitleaks` blocks secrets before commit and in GitHub Actions.
- `git-crypt` encrypts `vault/**` in Git history and on GitHub.
- deterministic tier checks block sensitive content in lower-trust folders.
- Claude passive prompt injection excludes `vault/` by default.
- explicit MCP tools are available for intentional vault search and reads.

Local plaintext exists after `git-crypt unlock`. Protect your workstation and
the exported git-crypt key accordingly.
