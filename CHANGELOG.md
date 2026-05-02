# Changelog

All notable changes to iContext will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.1] - 2026-05-02

### Fixed
- `cli.py` syntax error in `cmd_init` final message (escaped quote in f-string broke fresh installs)
- Doctor now recognizes skills-first install mode and downgrades legacy-mode checks to warns
- Doctor checks connector files at install root (`~/icontext/connectors/`), not inside vault
- Doctor `gitleaks` invocation uses `detect` subcommand (not the invalid `dir`)

### Added
- "How it works" technical depth section in README (synthesis pipeline, cross-tool support, privacy)
- CHANGELOG.md (Keep a Changelog format)

### Changed
- Skill `icontext-populate-profile`: tiered relationship threshold, project-vs-task distinction, explicit date instruction (raised dogfooded quality from 6.5/10 to 8/10)

## [0.2.0] - 2026-05-02

### Added
- Skills-first architecture: `icontext init` installs three skills into `~/.claude/skills/` and `~/.cursor/rules/`
  - `icontext-populate-profile`: agent-driven profile synthesis with cascade (Gmail MCP -> LinkedIn -> user-described)
  - `icontext-refresh-profile`: staleness handling for keeping profiles current
  - `icontext-share-card`: shareable summary card generation
- Modular profile output split across `user.md`, `relationships.md`, `projects.md`, `context-card.md`
- `icontext skills` subcommand (list, update)
- `icontext --version` flag
- Comparisons section in README covering mem0, OpenMemory, Obsidian, Pieces, CLAUDE.md, and Cursor Rules
- Demo GIF in README
- Threat model documented in SECURITY.md
- 80 tests across connectors, CLI, and doctor
- Polished CLI output with color and structure
- Copy-pasteable Claude prompt printed after `icontext init`
- Demo script and README quickstart

### Changed
- `icontext init` no longer requires a Gemini API key
- `icontext sync` (Gemini-driven) is now an optional headless fallback (`pip install icontext[sync]`)
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

Initial public release. Vault structure with sensitivity tier checks, MCP context index server, basic Gmail and LinkedIn connectors, icontext CLI, prompt hook for Codex/Cursor/OpenCode, and CI secret scanning via gitleaks.
