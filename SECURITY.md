# Security & Privacy

## Threat model

iContext stores sensitive personal data — email metadata, professional profile, synthesized identity. This document explains what we protect against, what we don't, and what you should know.

### What iContext protects against

- **Cloud breach**: Your data is never sent to any iContext server. There is no iContext server.
- **Synthesis provider breach**: Only the synthesized profile is sent to Gemini for processing. Raw email contents are never sent.
- **Repo leak (vault tier)**: Files in `vault/` are encrypted with git-crypt before commit. A leaked Git remote does not expose vault contents.
- **Pre-commit secret leak**: `gitleaks` runs as a pre-commit hook to catch credentials.

### What iContext does NOT protect against

- **Local machine compromise**: If your machine is compromised, all unencrypted vault tiers (`shareable/`, `internal/`) are accessible. Use full-disk encryption (FileVault on macOS).
- **Repo leak (other tiers)**: Files in `shareable/` and `internal/` are NOT encrypted in Git. Don't push your vault to a public repo.
- **App password compromise**: Gmail App Passwords are stored in your OS keychain, but they grant IMAP access. Treat them like passwords. Revoke at https://myaccount.google.com/apppasswords if compromised.
- **Gemini provider risk**: Synthesized profile content is sent to Google's Gemini API for processing. See Google's data handling: https://ai.google.dev/gemini-api/terms

## What data is read

### From Gmail (IMAP, headers only)

- Sender, recipient, subject line, date — for the last 90 days
- **NOT read**: message bodies, attachments, contact lists, settings

### From LinkedIn (PDF only)

- Whatever appears in the "Save to PDF" export of your profile (work history, education, skills, headline)
- **NOT read**: messages, connections list, feed activity, ads

## What data is stored

| Data | Where | Encrypted at rest |
|---|---|---|
| Gmail App Password | OS keychain (macOS Keychain / Linux Secret Service) | Yes (OS-managed) |
| Synthesized profile | `internal/profile/user.md` | No (use FileVault) |
| LinkedIn profile | `internal/profile/linkedin.md` | No (use FileVault) |
| Context card | `shareable/profile/context-card.md` | No (designed to be shared) |
| Connector config | `.icontext/connectors.json` | No (no secrets stored) |

## What data leaves your machine

| Destination | What | When |
|---|---|---|
| imap.gmail.com | Your Gmail credentials, your IMAP queries | During `icontext sync gmail` |
| generativelanguage.googleapis.com | Synthesized email summary (no raw content), LinkedIn PDF text | During `icontext sync` |
| Nothing else | — | — |

iContext makes no other network requests.

## Installer trust model

Run installs with `--dry-run` to inspect the exact plan before files change.
Without `--yes`, install uses an interactive confirmation gate. Use `--yes` only
when that plan is acceptable for non-interactive execution.

Install modes narrow the trust surface:

- `minimal` installs security config, local runtime, MCP server files, and
  manifest, with no hooks or CI.
- `standard` adds local Git hooks and the CI workflow.
- `agents` also updates selected local agent configs so those tools can call the
  local MCP server.

The manifest records icontext-managed files with repo-relative paths and hashes
for audit and uninstall. It intentionally avoids absolute local home paths. Run
`uninstall.sh --dry-run` to preview the manifest removals. Uninstall removes
icontext-managed hooks, runtime files, root config, workflow, and manifest; it
does not delete vault content.

Agent installation does not grant a remote service new direct access by itself.
It writes local MCP and hook configuration for tools already running under your
user account. Claude passive prompt context excludes `vault/` by default, while
explicit MCP reads remain intentional actions by the agent/tool you enabled.

## Reporting a vulnerability

Email security@floom.dev with details. We will respond within 48 hours.

Do not file public GitHub issues for security vulnerabilities.
