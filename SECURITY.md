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

## Installer Trust Model

Run installs with `--dry-run` to inspect the exact plan before files change.
Without `--yes`, install uses an interactive confirmation gate. Use `--yes` only
when that plan is acceptable for non-interactive execution.

Install modes narrow the trust surface:

- `minimal` installs security config, local runtime, MCP server files, and
  manifest, with no hooks or CI.
- `standard` adds local Git hooks and the CI workflow.
- `agents` also updates selected local agent configs so those tools can call the
  local MCP server.

The manifest records icontext-managed files for audit and uninstall. Run
`uninstall.sh --dry-run` to preview the manifest removals. Uninstall removes
icontext-managed hooks, runtime files, root config, workflow, and manifest; it
does not delete vault content.

Agent installation does not grant a remote service new direct access by itself.
It writes local MCP and hook configuration for tools already running under your
user account. Claude passive prompt context excludes `vault/` by default, while
explicit MCP reads remain intentional actions by the agent/tool you enabled.
