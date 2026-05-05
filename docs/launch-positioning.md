# Launch Positioning

## One-liner

`fbrain` is an encrypted AI context vault for Claude Code, Codex, Cursor, and
OpenCode.

## Short Description

Most AI coding agents can read a repo. `fbrain` makes a private context repo
safe and useful: Git-backed tiers, git-crypt encryption, gitleaks, local SQLite
retrieval, MCP tools, Claude prompt injection, multi-agent config, and a doctor
command that verifies the whole setup.

## Why It Matters

The real bottleneck in agentic work is not only model quality. It is trusted
context. Private strategy, legal files, credentials, notes, PDFs, and operating
memory are usually either inaccessible to agents or pasted into prompts without
controls.

`fbrain` turns that messy personal context into an operational substrate:
encrypted at rest in Git, guarded before commit and push, searchable locally,
and available to agents through explicit tools.

## What To Say

- "I stopped treating context as prompt scraps and turned it into infrastructure."
- "The vault became a working layer for Claude Code, Codex, Cursor, and OpenCode."
- "Every launch claim is backed by `doctor.py`: encryption, hooks, MCP, agents,
  CI, gitleaks, and retrieval eval."

## What Not To Say

- Do not claim it replaces full knowledge management systems.
- Do not claim semantic search is solved; current retrieval is SQLite FTS.
- Do not present it as a hosted product.
- Do not imply vault content is safe after the git-crypt key is leaked.

## Launch Post Draft

I built `fbrain`: an encrypted AI context vault for Claude Code, Codex,
Cursor, and OpenCode.

The idea is simple: your private context repo is too valuable to stay as loose
Markdown and too sensitive to paste into prompts.

`fbrain` gives it structure:

- `shareable/`, `internal/`, and encrypted `vault/` tiers
- git-crypt encryption for sensitive history
- gitleaks locally and in CI
- deterministic tier checks before push
- local SQLite FTS retrieval
- MCP tools for agent access
- Claude prompt injection with conservative defaults
- a doctor command that proves the whole setup works

This changed how I work. My agents now have access to the context they need
without turning my private operating system into prompt soup.

Repo: https://github.com/floomhq/fbrain
