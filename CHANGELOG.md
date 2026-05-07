# Changelog

All notable changes to fbrain will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.5.1] - 2026-05-06

### Changed
- `fbrain-write-fact`: expanded trigger phrases. Now matches natural-language updates like "lets update fbrain", "update X's timeline", "extend X's record", "add to my legal record", and the legacy "icontext" aliases.
- `fbrain-write-fact`: new top-level decision branch for **extending an existing structured doc** (TIMELINE.md, status.md, profile.md). Tells the agent to find the canonical doc and append in place instead of creating a parallel log entry.
- `fbrain-write-fact`: explicit anti-pattern callout against dual-writing the same content to both a log file AND a structured doc.
- `fbrain-write-fact`: worked examples added for the most common update patterns (cursor-fraud TIMELINE, Finom log entry, Floom Inc registration, team status update).

### Why
A Kimi session received "lets update icontext?" and did not pattern-match the skill description. It ended up dual-writing the same content to both a log file AND TIMELINE.md. This release fixes both gaps.

## [0.5.0] - 2026-05-06

### Changed
- Renamed the Python package, primary CLI, documentation, MCP server branding, and user-facing scripts from fbrain's former `icontext` name to `fbrain`.
- `fbrain` is now the canonical command and package name.
- Renamed canonical skills to `fbrain-populate-profile`, `fbrain-refresh-profile`, `fbrain-share-card`, and `fbrain-write-fact`.

### Deprecated
- `icontext` remains available as a CLI shim for one release cycle. It prints a deprecation warning and forwards to `fbrain`; removal is planned for v0.6.0.
- `skills/icontext-*` remain as deprecated redirect stubs for one release cycle; removal is planned for v0.6.0.

## [0.4.0] - 2026-05-04

### Added
- **`fbrain-write-fact` skill.** Explicit decision tree that routes content to the correct vault location before writing. Covers six categories: legal/entity facts (`vault/legal/`), project facts (`vault/projects/`), team/people (`vault/team/`), strategy (`vault/strategy/`), secretarial activity (`vault/secretary/logs/`), and credentials. Includes a full top-level vault directory reference so agents can match against the real structure without guessing. Eliminates the recurring "agent dumps legal facts in log files" failure mode.
- `fbrain-populate-profile` now references `fbrain-write-fact` for any durable facts surfaced during profile synthesis (e.g. company registrations, attorney contacts, funding dates).
- `fbrain-write-fact` ships with `fbrain init` — installed to `~/.claude/skills/` and `~/.cursor/rules/` alongside the existing three skills.
- CLAUDE.md snippet updated to list all four skills.
- Tests for the new skill: frontmatter, decision tree category coverage, init installation, Cursor rule, skills-list count, and CLAUDE.md reference.

### Changed
- Bumped version to 0.4.0.

## [0.3.0] - 2026-05-02

### Added
- **Multi-device sync.** Your vault now follows you across machines via a private git remote.
  - `fbrain push` — commit and push local changes to origin
  - `fbrain pull` — rebase against origin with autostash (last-writer-wins, surfaces conflicts)
  - `fbrain autosync start|stop|status` — background agent that runs `fbrain push` every 60 seconds
    - macOS: `launchd` at `~/Library/LaunchAgents/dev.fbrain.autosync.plist`
    - Linux: `systemd --user` timer at `~/.config/systemd/user/fbrain-autosync.timer`
- `user-prompt-submit` hook now pulls from origin in the background if a remote is configured, so Claude Code sees fresh context from other machines at the start of every prompt.
- CLAUDE.md snippet references the multi-device sync workflow.
- Tests for `push`, `pull`, and `autosync` (--help, no-origin hint, status reports not running on clean home).

### Changed
- Bumped version to 0.3.0.

## [0.2.1] - 2026-05-02

### Fixed
- `cli.py` syntax error in `cmd_init` final message (escaped quote in f-string broke fresh installs)
- Doctor now recognizes skills-first install mode and downgrades legacy-mode checks to warns
- Doctor checks connector files at install root (`~/fbrain/connectors/`), not inside vault
- Doctor `gitleaks` invocation uses `detect` subcommand (not the invalid `dir`)

### Added
- "How it works" technical depth section in README (synthesis pipeline, cross-tool support, privacy)
- CHANGELOG.md (Keep a Changelog format)

### Changed
- Skill `fbrain-populate-profile`: tiered relationship threshold, project-vs-task distinction, explicit date instruction (raised dogfooded quality from 6.5/10 to 8/10)

## [0.2.0] - 2026-05-02

### Added
- Skills-first architecture: `fbrain init` installs three skills into `~/.claude/skills/` and `~/.cursor/rules/`
  - `fbrain-populate-profile`: agent-driven profile synthesis with cascade (Gmail MCP -> LinkedIn -> user-described)
  - `fbrain-refresh-profile`: staleness handling for keeping profiles current
  - `fbrain-share-card`: shareable summary card generation
- Modular profile output split across `user.md`, `relationships.md`, `projects.md`, `context-card.md`
- `fbrain skills` subcommand (list, update)
- `fbrain --version` flag
- Comparisons section in README covering mem0, OpenMemory, Obsidian, Pieces, CLAUDE.md, and Cursor Rules
- Demo GIF in README
- Threat model documented in SECURITY.md
- 80 tests across connectors, CLI, and doctor
- Polished CLI output with color and structure
- Copy-pasteable Claude prompt printed after `fbrain init`
- Demo script and README quickstart

### Changed
- `fbrain init` no longer requires a Gemini API key
- `fbrain sync` (Gemini-driven) is now an optional headless fallback (`pip install fbrain[sync]`)
- Synthesis pipeline rewritten as 3-stage architecture (extract -> validate -> render), used by optional sync
- README hero rewritten around "Your AI agents now share a brain"
- Replaced ai-sidecar dependency with Gemini SDK; credentials now stored via OS keychain

### Fixed
- f-string syntax error in `cmd_init` final message (220e187)
- IMAP timeout on slow connections
- Self-relationship detection: filter out fede@floom.dev style alias addresses
- SaaS welcome senders no longer hallucinate as key relationships
- Direction conflation in email parsing
- RFC 2822 folded header support via `email.parser.BytesParser`
- Critical runtime bugs: TypeError, model 404, partial save, argparse errors

### Security
- Gmail App Passwords stored in OS keychain via `keyring`, never plaintext JSON
- Threat model documented in SECURITY.md
- gitleaks pre-commit hook added to CI
- Personal email addresses and hardcoded paths removed from public release

## [0.1.0] - 2026-04-26

Initial public release. Vault structure with sensitivity tier checks, MCP context index server, basic Gmail and LinkedIn connectors, fbrain CLI, prompt hook for Codex/Cursor/OpenCode, and CI secret scanning via gitleaks.
