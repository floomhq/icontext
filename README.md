# fbrain

[![CI](https://github.com/floomhq/fbrain/actions/workflows/ci.yml/badge.svg)](https://github.com/floomhq/fbrain/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/floomhq/fbrain)](https://github.com/floomhq/fbrain/stargazers)

![fbrain demo](demo/icontext-demo.gif)

**Your AI agents now share a brain.**

fbrain is a folder + a set of skills. Your AI tools (Claude Code, Cursor, Codex) read from it before answering, and write to it as they learn about you. Local. Encrypted. No API keys.

## Quickstart

```bash
curl -fsSL https://raw.githubusercontent.com/floomhq/fbrain/main/get.sh | bash
fbrain init
```

Deprecated one-release alias, retained for existing install docs:

```bash
curl -fsSL https://raw.githubusercontent.com/floomhq/icontext/main/get.sh | bash
icontext init
```

Open Claude Code and say: **"Populate my fbrain profile."**

That's it. Your AI now has persistent memory.

## How it works

fbrain is intentionally minimal infrastructure. Three pieces:

### 1. The vault — a structured folder

Plain Markdown files in a tiered folder structure:

```
~/context/
  internal/profile/
    user.md            # full synthesized profile (identity, relationships, topics, projects, communication, pending)
    relationships.md   # key contacts table
    projects.md        # active projects
  shareable/profile/
    context-card.md    # 200-word shareable summary, safe to send to collaborators
  vault/               # git-crypt encrypted (legal docs, credentials, anything truly private)
```

Every file is plain Markdown. Open it in a text editor, in Obsidian, or pipe it to any tool. No proprietary format.

### 2. Skills — instructions your AI agent follows

`fbrain init` installs four skills:

- **fbrain-populate-profile** — builds the profile from real data sources
- **fbrain-refresh-profile** — updates a stale profile
- **fbrain-share-card** — regenerates the shareable summary
- **fbrain-write-fact** — routes durable facts to the right vault location

Skills are Markdown files installed at:
- `~/.claude/skills/fbrain-*/SKILL.md` (Claude Code)
- `~/.cursor/rules/fbrain-*.mdc` (Cursor)

When you ask Claude Code "populate my fbrain profile", it discovers the skill via its description, reads the instructions, and executes them.

### 3. The synthesis pipeline

The populate skill instructs the agent to follow a deterministic 4-stage flow:

**Stage A — Source cascade (try in order):**
1. Gmail MCP if available (read headers only — never message bodies)
2. LinkedIn via browser automation, or a saved-to-PDF profile
3. User describes themselves in chat (4 questions)

**Stage B — Entity extraction:**
The agent extracts structured data from the source: people (with evidence_messages count), projects (with evidence_subjects), topics. Filters out 1-shot SaaS welcome emails, notification senders, and self-addresses.

**Stage C — Local validation:**
- Drop entities below evidence threshold (≥2 messages for relationships, ≥2 subjects for projects)
- Dedupe by email/handle
- Sort by evidence weight, keep top 15-20

**Stage D — Markdown rendering:**
Write four files (`user.md`, `relationships.md`, `projects.md`, `context-card.md`) using a fixed template. Roles and context columns are required (cite subject evidence, never blank). No HTML comment delimiters or fragile parsing.

This is the same architecture as the optional headless `fbrain sync` (which uses Gemini 2.5 Flash Lite directly), just executed by the user's AI agent instead.

### Cross-tool: every agent reads the same folder

| Tool | How it reads | How it writes |
|---|---|---|
| Claude Code | CLAUDE.md snippet + skill files | Skill file invocation |
| Cursor | `.cursor/rules/fbrain-*.mdc` | Same skill instructions, Cursor-flavored |
| Codex | reads vault directly (plain MD) | optional — `fbrain sync` |
| OpenCode | reads vault directly (plain MD) | optional — `fbrain sync` |

Any tool that can read Markdown can read the vault. Any tool that can follow Markdown instructions can populate it.

### Privacy and security

- **No external API calls by default.** Synthesis happens inside your AI agent's session. No fbrain server, no telemetry, no profile leaves your machine.
- **Credentials in OS keychain.** Gmail App Passwords (only used for the optional headless `sync`) are stored via `keyring` — macOS Keychain, Linux Secret Service. Never in plaintext JSON.
- **Vault tier encryption.** `vault/` is git-crypt encrypted at rest. `internal/` and `shareable/` are plaintext (designed to be portable and readable in Obsidian).
- **Pre-commit secret scanning.** `gitleaks` runs on every commit if you push the vault to git.

Full threat model in [SECURITY.md](SECURITY.md).

## What you get

```text
~/context/
  shareable/        public-safe summaries
    profile/
      context-card.md   sendable to collaborators
  internal/         private working context
    profile/
      user.md           full profile
      relationships.md  key contacts
      projects.md       active projects
  vault/            git-crypt encrypted secrets
```

Then your agents share the same context layer:

```text
Claude Code   →  skills + CLAUDE.md
Cursor        →  rules
Codex / OpenCode  →  optional MCP server (legacy)
GitHub        →  gitleaks + tier CI
```

## Privacy

Synthesis runs inside your AI agent's session, not on a server. Default install requires no API keys. Email metadata never leaves your laptop.

fbrain stores:

- Your synthesized profile in `~/context/internal/profile/`. Plaintext on disk. Use FileVault.
- Your vault secrets in `~/context/vault/`. Encrypted with `git-crypt`.

fbrain does not run a server. No data is ever sent to any fbrain-controlled endpoint.

Full threat model: see [SECURITY.md](SECURITY.md).

## Headless / no-agent setup (optional)

If you don't have Claude Code or Cursor and want a fully automated pipeline, the original Gemini-based sync is still available:

```bash
pip install fbrain[sync]
fbrain connect gmail
fbrain connect linkedin --pdf ~/Downloads/Profile.pdf
fbrain sync
```

This requires `GEMINI_API_KEY` and runs the same 3-stage synthesis as the agent skill, but headlessly. Use it for CI, scripts, or non-agent environments.

## Features

| Layer | What fbrain does |
|---|---|
| Skills | Markdown instructions your agent follows to populate and refresh your profile. |
| Encryption | `vault/**` is protected with `git-crypt` in Git and on GitHub. |
| Secret scanning | `gitleaks` runs locally and in GitHub Actions. |
| Tier enforcement | deterministic classifier blocks sensitive files in lower-trust folders. |
| Retrieval | local SQLite FTS index, rebuilt by hook, no API key required. |
| MCP (optional) | `search_vault`, `read_vault_file`, `append_log`, `rebuild_index`. |
| Verification | `doctor.py --deep` checks hooks, encryption, index, MCP, agents, gitleaks, and CI. |
| Headless sync | optional Gemini-based fallback for CI / no-agent setups. |

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
curl -fsSL https://raw.githubusercontent.com/floomhq/fbrain/main/get.sh | bash
fbrain init
```

Deprecated alias for this release:

```bash
curl -fsSL https://raw.githubusercontent.com/floomhq/icontext/main/get.sh | bash
icontext init
```

Or manually:

```bash
git clone https://github.com/floomhq/fbrain ~/fbrain
pip install -e ~/fbrain
fbrain init
```

`fbrain init` creates the vault, installs skills into `~/.claude/skills/` and `~/.cursor/rules/`, and adds a CLAUDE.md snippet so your agent loads the profile at session start.

### Skill management

```bash
fbrain skills list      # show installed skills and where they live
fbrain skills update    # pull latest skill versions from the fbrain repo
```

## Prove it works

```bash
fbrain doctor
```

The doctor command validates your install without starting background services or adding hosted dependencies.

## Uninstall

```bash
bash ~/fbrain/uninstall.sh /path/to/vault
```

Uninstall removes fbrain-managed hooks, `.icontext/`, the GitHub Actions workflow, and the install manifest. It leaves your `shareable/`, `internal/`, and `vault/` content in place.

## Requirements

- `git`
- Python 3.11+

Optional:

- `gitleaks` for secret scanning (`brew install gitleaks`)
- `git-crypt` for vault encryption (`brew install git-crypt`)
- `git-lfs` for binary assets (`brew install git-lfs`)
- `GEMINI_API_KEY` only if you want the headless `fbrain sync` fallback

## Multi-device sync

Same vault, every machine. fbrain uses git on a private repo as the sync layer — no extra service, no daemon talking to a vendor.

### Setup (3 steps)

On your **primary machine**, push the vault to a private repo:

```bash
cd ~/context
gh repo create <user>/context --private --source=. --push
fbrain autosync start          # commits + pushes every 60s
```

On every **other machine**, clone and start autosync:

```bash
gh repo clone <user>/context ~/context
fbrain autosync start
```

That's it. Edits made on machine A appear on machine B within ~60s of the next prompt (the `user-prompt-submit` hook also pulls in the background whenever you start a Claude Code prompt).

### Commands

| Command | What it does |
|---|---|
| `fbrain push` | Commit local changes and push to origin |
| `fbrain pull` | Rebase against origin (autostashes in-flight changes) |
| `fbrain autosync start` | Install + start the 60s background agent |
| `fbrain autosync stop` | Stop and remove the agent |
| `fbrain autosync status` | Show running state and last sync time |

### Conflict handling

`fbrain pull` runs `git pull --rebase --autostash`. Last writer wins. If two machines edit the same lines of the same file in the same minute, the rebase surfaces the conflict and prints the file paths — resolve manually with normal git tooling.

In practice, conflicts are rare: profile files are append-mostly, and the 60s push window is shorter than typical edit cycles.

### Implementation

- macOS: `launchd` agent at `~/Library/LaunchAgents/dev.fbrain.autosync.plist`. Logs at `~/Library/Logs/fbrain.log`.
- Linux: `systemd --user` timer at `~/.config/systemd/user/fbrain-autosync.timer`. Logs via `journalctl --user -u fbrain-autosync.service`.

## How fbrain compares

Common question: "isn't this just like X?"

| | What it is | How fbrain is different |
|---|---|---|
| **mem0 / Letta / Zep** | Memory libraries for developers building agents | fbrain is for end users; you don't write code to use it |
| **OpenMemory** | Local CLI + MCP for AI memory | OpenMemory's memory is reactive (built from chat history). fbrain is proactive (built from your real data: Gmail, LinkedIn) |
| **Obsidian** | Knowledge base for humans | Obsidian is for humans writing notes; fbrain is for AI agents writing context. Same folder works for both — open ~/context in Obsidian for the human view. |
| **Pieces.app** | OS-level capture for developers | Pieces captures what you do; fbrain synthesizes who you are. Different layer. |
| **Claude Code's CLAUDE.md** | Per-project AI instructions | CLAUDE.md is per-project. fbrain is your *identity* — the same context every project uses. |
| **Cursor Rules / .cursorrules** | Cursor-specific instructions | fbrain works across Claude Code, Cursor, Codex, OpenCode via MCP and shared file conventions. Tool-agnostic. |

The wedge: **fbrain is the only tool that proactively builds your professional identity from sources you already own (Gmail, LinkedIn) and exposes it to every AI tool you use.**

## Status

Production-ready. Run `fbrain doctor` to verify your install.

> Social preview image at `assets/og-image.png` — upload via Settings → Social preview

## Built with fbrain

*Share your setup: tag #fbrain on Twitter/X*
