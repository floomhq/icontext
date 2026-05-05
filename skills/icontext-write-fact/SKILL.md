---
name: icontext-write-fact
description: >
  Decide WHERE to write a fact, document, or piece of context in the iContext
  vault. Use whenever you need to persist a fact (legal entity info, project
  status, contact details, decision rationale) that doesn't fit neatly into
  the synthesized profile. Prevents agents from dumping everything into
  log files.
  Triggers: "save to vault", "store this in icontext", "persist this", "add to
  my context", "remember this", "write this down", "log this".
---

# iContext: Write a Fact to the Vault

When asked to save something to the vault, use this decision tree FIRST. Do NOT default to log files.

## Decision tree

### Is it a legal/entity/compliance fact?

Examples: company registration, EIN, VAT ID, articles of incorporation, jurisdiction, registered agent, attorney contact, contracts, NDAs, cap table entries.

Route to: `vault/legal/<entity>.md` (e.g. `vault/legal/floom-inc.md`, `vault/legal/scaile-gmbh.md`)

- For ongoing matters or disputes: `vault/legal/incidents/<incident>/`
- For contracts with a specific party: `vault/legal/contracts/<counterparty>.md`

### Is it about a specific project?

Examples: launch plans, user research, technical decisions, project status, KPIs, GTM specifics, workplans, feature flags, error logs tied to a project.

Route to: `vault/projects/<project>/<topic>.md`

- For sub-streams: `vault/projects/<project>/<stream>/<topic>.md`
- Known project slugs: `floom`, `rocketlist`, `openpaper`, `signaldash`, `cheers`, `agora`, `hyperniche`

### Is it about a person on your team or in your network?

Examples: a team member's role and scope, an investor's interest area, a recurring collaborator's background, hiring notes.

Route to:

- Your own team: `vault/team/<entity>/<person>.md` (e.g. `vault/team/floom/cedrik.md`)
- External relationships you actively track: `vault/network/<person-or-org>.md`

### Is it strategy or roadmap?

Examples: 90-day plan, market positioning, fundraising strategy, OKRs, go-to-market thesis, competitive analysis.

Route to: `vault/strategy/<topic>.md` or `vault/strategy/<entity>/<topic>.md`

### Is it a one-off note or in-progress thought?

Examples: "I should remember to ask X about Y", "interesting thing I noticed", informal to-do.

Route to: `vault/notes/<topic>.md` or `internal/scratch/<topic>.md`

Do NOT put this in logs. Logs are time-stamped activity records.

### Is it secretarial activity?

Examples: "Sent legal letter 16 to Finom on 2026-04-30", "Meeting with Garima at Founders Inc 2026-05-02", "Completed task X".

Route to: `vault/secretary/logs/YYYY-MM.md` (one file per month, append to it)

This is the ONLY category that belongs in log files.

### Is it credentials or secrets?

Examples: API keys, OAuth tokens, app passwords, certificates.

Do NOT write to vault. Use OS keychain (`keyring` library) or password manager. If absolutely necessary and the vault has git-crypt active: `vault/credentials/<service>.md` with a clear warning header.

### Does it fit an existing top-level vault directory?

Before creating a new top-level directory, check whether content fits one of the established categories:

- `vault/applications/` — job or program applications
- `vault/brand/` — logos, brand assets, visual guidelines
- `vault/content/` — LinkedIn posts, blog drafts, social copy, transcripts
- `vault/cv/` — CV and resume versions
- `vault/documents/` — official documents, certificates, diplomas
- `vault/infra/` — server setup, config, tools, scripts
- `vault/legal/` — legal entities, contracts, incidents
- `vault/partnerships/` — active partnership threads
- `vault/pitches/` — investor decks, pitch materials
- `vault/projects/` — active or past product projects
- `vault/research/` — market research, user research, analysis
- `vault/secretary/` — admin, logs, state, scheduling
- `vault/skills/` — custom agent skills
- `vault/strategy/` — plans, positioning, OKRs
- `vault/taxes/` — tax filings and records by entity
- `vault/team/` — team members by entity
- `vault/travel/` — travel plans, attachments

If none fit: pick the closest, add a sub-directory, and do not invent a new top-level category without asking.

## How to actually save

After picking the target path:

1. **Check if the file already exists.** If yes, append a new section (with a date or topic header) instead of overwriting.

2. **Use appropriate structure.** For `vault/legal/<entity>.md`:

   ```markdown
   # <Entity Name>

   ## Registration
   - **Type**: <C-Corp / GmbH / LLC>
   - **Jurisdiction**: <Delaware / Hamburg / etc>
   - **Incorporated**: <date if known>
   - **EIN / VAT / Tax ID**: <if known>
   - **Registered agent**: <if applicable>

   ## Officers / Directors
   ...

   ## Founding documents
   ...
   ```

3. **Commit with a descriptive message:**

   ```bash
   git add vault/legal/floom-inc.md
   git commit -m "vault: add Floom Inc Delaware registration"
   ```

   git-crypt encrypts on stage automatically if the machine has git-crypt configured.

4. **NEVER append legal/entity/durable facts to log files.** Logs are time-stamped activity. Facts are searchable references that must stay in the correct category directory.

## Anti-patterns

- Storing company registration in `vault/secretary/logs/icontext.md` — this is the bug this skill exists to prevent
- Storing meeting notes in `vault/legal/`
- Storing contact details for a team member in `vault/strategy/`
- Creating a new top-level vault directory when an existing one fits
- Overwriting an existing file instead of appending a new section

## When uncertain

If a fact doesn't fit any category cleanly, ask the user where they want it before guessing. One specific question is cheaper than burying a durable fact in a log the user has to dig out later.
