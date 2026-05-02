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

**People** (only if there is evidence of a real relationship):

- name, email/handle, company, role
- evidence_messages: count of bidirectional contact (need >= 2)
- direction: mostly_inbound | mostly_outbound | balanced
- topics: 2-3 subject patterns

**EXCLUDE these as people:**

- SaaS welcome emails (welcome@, no-reply@, team@ from a domain you only see once)
- Notification senders (notifications@, alerts@, support@)
- Billing/payment processors unless they appear in active threads
- Anyone you only have 1 message from total

**Projects** (need >= 2 evidence subjects to qualify):

- name, description, evidence_subjects (the actual subject lines)

**Topics**: recurring themes (5-10 phrases)

### Stage B: validate locally

- Drop people with <2 messages.
- Dedupe entities by email/handle.
- Detect self-addresses (forwards to alternate emails of the same user) and exclude them.
- Sort people by evidence weight, keep top 15-20.

### Stage C: write the profile

Write THREE files in `~/context/internal/profile/`:

#### user.md (full profile)

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
