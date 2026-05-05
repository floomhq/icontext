---
name: icontext-refresh-profile
description: >
  Update an existing iContext profile when it has gone stale. Use when the user
  asks to "refresh my profile", "update my context", "re-scan my email", or
  when internal/profile/user.md exists but the `generated:` date is older than
  7 days. Delegates to icontext-populate-profile but only writes if data has
  meaningfully changed.
---

# iContext: Refresh Profile

Update the user's profile in `~/context/internal/profile/` when it has gone stale. This is a delta-aware wrapper around `icontext-populate-profile`.

## When to use

Trigger this skill when:

- The user explicitly asks to refresh, update, re-scan, or sync their profile.
- A previous session detected the profile is older than 7 days.
- The user mentions a major life or work change ("I left X", "I'm now working on Y") that may have invalidated stored relationships and projects.

## Pre-flight checks

1. Read `~/context/internal/profile/user.md`. If it does not exist, route to `icontext-populate-profile` instead.
2. Parse the `generated:` field from the frontmatter.
3. Compute age:
   - <7 days: ask the user "your profile was refreshed N days ago, force a refresh anyway?". If no, stop.
   - 7-30 days: proceed without asking.
   - >30 days: proceed and note the staleness in your final summary.
4. Read `~/context/internal/profile/relationships.md` and `projects.md` to capture the prior state.

## Refresh procedure

Follow the cascade from `icontext-populate-profile`:

1. Gmail MCP (preferred).
2. LinkedIn (browser or PDF).
3. User-described (only if both fail).

Do NOT mix sources. Pick the highest-quality available source and rebuild from it. The point of refresh is to capture changes, not to merge stale data.

### Delta semantics

After running Stage A and Stage B from `icontext-populate-profile`:

- Compare the new candidate set vs the prior `relationships.md` and `projects.md`.
- If the diff is trivial (no new people, no new projects, no removed people, no new topics): skip the write and tell the user "no meaningful changes since {prior_date}".
- If there is meaningful change: write all four files (user.md, relationships.md, projects.md, context-card.md) using Stage C and Stage D from `icontext-populate-profile`.

A "meaningful change" is any of:

- A new person enters the top 15 relationships.
- A person drops out of the top 15 (e.g. you stopped emailing them).
- A new project appears with >= 2 evidence subjects.
- A previously-active project loses all evidence (status: archived).
- The dominant topics shift by more than 2 entries.

### Frontmatter

When writing, update the frontmatter:

```yaml
---
generated: YYYY-MM-DD
sources: gmail, linkedin
previous_generated: {prior_date_from_old_file}
---
```

This gives future refresh runs a trail of when the profile last meaningfully changed.

## Changelog

After a write (skip if no meaningful changes), append one line to `~/context/internal/changes.md`:
```
YYYY-MM-DD: refresh — <changed/no change>, source: <source>
```

## Output

Summarize for the user:

- Source used.
- Whether there were meaningful changes (yes/no).
- If yes: bullet list of what changed (new people, removed people, new projects, archived projects).
- If no: confirm the profile is still accurate as of {prior_date}.
- File paths written (or "no files written" if skipped).

## Voice rules

Inherit from `icontext-populate-profile`. Plain second person, no buzzwords, no em dashes, evidence-grounded.
