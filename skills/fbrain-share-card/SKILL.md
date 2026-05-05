---
name: fbrain-share-card
description: >
  Regenerate the user's shareable context card from existing profile data. Use
  when the user asks to "share my context", "generate a context card", "make
  a one-pager about me", or when they want a sendable summary for a
  collaborator. No external data fetch. Reads ~/context/internal/profile/ and
  writes ~/context/shareable/profile/context-card.md.
---

# fbrain: Share Card

Generate a public-safe one-page context card from the user's existing profile. This skill never fetches external data. It only synthesizes from what is already in `~/context/internal/profile/`.

## When to use

- The user wants something they can paste into an email, Slack, or a new AI session.
- The user wants to update the card without re-scanning Gmail.
- The user is onboarding a new collaborator and wants a brief intro.

## Pre-flight checks

1. Read `~/context/internal/profile/user.md`. If missing, route to `fbrain-populate-profile`. Do NOT fabricate the card.
2. Read `~/context/internal/profile/projects.md` and `relationships.md` for additional grounding.

## Output spec

Write `~/context/shareable/profile/context-card.md`:

```markdown
---
shareable: true
generated: YYYY-MM-DD
source: internal/profile/user.md
---

# {Name}

**Building:** {1-line of current primary work with company/project name}
**Background:** {2 sentences on past + scale (companies, ARR, team size, education only if relevant)}
**Currently focused on:**
* {3-5 active threads from projects.md, one line each}
**Best way to work with them:** {2 sentences inferred from communication style in user.md}
```

## Hard rules

- **200-word max.** Count words. Trim if over.
- **No corporate filler.** Banned phrases: "passionate about", "pioneering", "leveraging", "synergy", "thought leader", "proven track record", "results-driven", "innovative".
- **No em dashes.** Use commas, semicolons, colons.
- **Plain second person** ("you are working on", "you previously built").
- **Evidence-grounded.** Every claim must be traceable to user.md, projects.md, or relationships.md. If you cannot find evidence, leave it out rather than invent.
- **No private relationship details.** The card is shareable. Don't list specific contacts by name unless they are public collaborators (co-founders, public team members). Aggregate ("frequent collaborator on X") is fine.
- **No email addresses, no phone numbers, no home addresses.**

## Voice calibration

The card sounds like the user, not like a recruiter. If `user.md` shows the user writes short, direct sentences, the card writes short, direct sentences. If `user.md` shows technical language, the card uses technical language.

Read 2-3 samples from `user.md` Communication Patterns section before drafting to calibrate.

## Output

After writing, summarize for the user:

- File path written.
- Word count.
- Suggested uses: "paste into a new AI session, email a collaborator, or drop into a shared vault".
- Offer: "want to tweak any line?"
