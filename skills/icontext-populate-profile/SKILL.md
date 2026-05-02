---
name: icontext-populate-profile
description: >
  Build the user's iContext profile from real data sources. Use when the user
  asks to "populate my profile", "build my context", "set up icontext", or when
  internal/profile/user.md is missing. Cascades through Gmail MCP -> browser
  scrape -> PDF -> user-described, picking the highest-quality source available.
---

# iContext: Populate Profile

Build a structured user profile in `~/context/internal/profile/` from real-world data sources. Follow the cascade in order. Use the highest-quality source available.

## Source cascade (try in order)

### 1. Gmail (highest quality)

If a Gmail MCP server is available (e.g. `mcp__gmail__*` or `mcp__claude_ai_Gmail__*` tools), use it:

- Fetch last 90 days of sent + inbox metadata (subject, from, to, date, cc).
- DO NOT fetch message bodies. Headers only.
- Run the synthesis pipeline in the next section.

### 2. LinkedIn (if available)

If browser automation is available (Playwright MCP, claude-in-chrome, etc.):

- Navigate to the user's LinkedIn profile (ask for the handle if you do not know it).
- Capture work history, education, skills, headline.

If browser automation is not available:

- Ask the user to "Save to PDF" their LinkedIn profile (linkedin.com/in/them -> More -> Save to PDF).
- Read the PDF text via the `pdf` skill or pypdf.

### 3. User-described (lowest friction, lowest quality)

If neither of the above works, ask the user 4 questions:

- What are you working on right now?
- What companies/projects matter to you?
- Who do you collaborate with most?
- What is your background in 2-3 sentences?

## Synthesis rules (apply to whatever data you collected)

### Stage A: extract structured entities

From the data, extract:

**People** (only if there is evidence of a real human relationship):

- name, email/handle, company, role
- evidence_messages: count of real messages (sent + received combined). Minimum threshold: >= 1 message involving a real named person (not a bot or service). Tier A (hot/warm) = 3+ messages or bidirectional contact. Tier B (cold) = 1-2 messages but clearly human and named.
- direction: mostly_inbound | mostly_outbound | balanced
- topics: 2-3 subject patterns

**EXCLUDE these as people:**

- SaaS welcome emails (welcome@, no-reply@, noreply@, team@ from a SaaS domain you only see once)
- Notification senders (notifications@, alerts@, support@, github-actions[bot], dependabot[bot])
- Billing/payment processors (payments-noreply@, failed-payments@) unless they appear in active human threads
- Automated systems (Cal.com booking confirmations, npm publish notifications, Vercel deploy alerts)
- Anyone where the sender is clearly a bot, automated pipeline, or service account

**Projects** (need >= 2 evidence subjects to qualify):

- name, description, evidence_subjects (the actual subject lines)
- PROJECTS only: active work the user is building, shipping, or growing. NOT one-time tasks, admin items, legal filings, or calendar events. "Immigration lawyer consultation" is a task, not a project. "Floom" is a project. "Rocketlist" is a project. When in doubt: would this have a GitHub repo or a recurring roadmap? If yes, it's a project.

**Topics**: recurring themes (5-10 phrases)

### Stage B: validate locally

- Drop bots, service accounts, and automated senders (see EXCLUDE list above).
- Keep all named humans with >= 1 real message, even if thin.
- Dedupe entities by email/handle.
- Detect self-addresses (forwarding/cc to alternate emails of the same user) and exclude them from relationships. Self-memos (user emailing themselves) are useful as project/topic evidence only.
- Sort people by evidence weight (Tier A first), keep top 15-20.
- If fewer than 3 people qualify after filtering, lower your standards: include Tier B contacts (single message, clearly human).

### Stage C: write the profile

Write THREE files in `~/context/internal/profile/`:

#### user.md (full profile)

**IMPORTANT: Use today's actual date for the `generated:` field. Do NOT use a date from training data or memory. If you know the current date, use it. If not, write `generated: [TODAY'S DATE]` as a placeholder.**

```markdown
---
generated: YYYY-MM-DD
sources: gmail, linkedin
---

## Identity Summary
{2-3 sentences. Plain second person. Cite real projects and current focus.}

## Key Relationships
| Name | Company | Role | Frequency | Warmth | Context |
|------|---------|------|-----------|--------|---------|
... required: ALWAYS fill role and context with evidence from subjects.
        NEVER leave blank. If thin, write the subject pattern as evidence.

## Recurring Topics
- {topic - how it appears}

## Active Projects
- **{name}** - {1-line status, cite evidence subjects}

## Communication Patterns
{3-4 sentences naming top inbound senders, top outbound recipients, dominant
topics, response style. Use real names.}

## Pending / Watch
- {item - concise present-tense, dedupe near-duplicates}
```

#### relationships.md

Just the Key Relationships table from above.

#### projects.md

Just the Active Projects section.

### Stage D: write context card

Write `~/context/shareable/profile/context-card.md`:

```markdown
---
shareable: true
generated: YYYY-MM-DD
---

# {Name}

**Building:** {1-line of current primary work with company/project name}
**Background:** {2 sentences on past + scale}
**Currently focused on:**
* {3-5 active threads, one line each}
**Best way to work with them:** {2 sentences inferred from communication style}
```

Strict 200-word max. No corporate filler. No "passionate about", no "pioneering". Plain second person. The user's actual voice from their actual data.

## Voice rules

- Plain second person ("you are", "you work on")
- No buzzwords ("synergy", "leveraging", "passionate")
- No em dashes
- Cite real names, real subjects, real projects
- If uncertain, say so in [brackets] rather than fabricating
- Always ground claims in evidence

## Refresh logic

If `internal/profile/user.md` exists:

- Check `generated:` date in frontmatter.
- If <7 days old: skip unless the user explicitly asks.
- If 7-30 days old: ask the user "your profile is N days old, refresh?"
- If >30 days old: refresh automatically.

## Output

After writing, summarize for the user:

- Source used (Gmail / LinkedIn / described)
- Number of relationships, projects, topics extracted
- File paths written
- Suggested next: "Open a new Claude Code session and ask me what I know about you."
