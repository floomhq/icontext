---
name: fbrain-enrich
description: >
  Update a single person or project entry in the fbrain vault from the current
  conversation. Use when the user says "I just spoke to X", "update X in my
  brain", "enrich X", or "add note about X".
---

# fbrain: Enrich One Entry

Update one existing person or project entry without rerunning populate or refresh.

## Trigger

Use this skill when the user asks to enrich, update, or add a note about one
person or project.

## Target

1. Identify the target name from the user's message.
2. Read `~/context/internal/profile/relationships.md` and
   `~/context/internal/profile/projects.md`.
3. Match the target against exactly one existing person or project entry.
4. If there is no clear match, ask one short clarification question.

## Source

Use only the current conversation context:

- the user's message
- recent tool outputs in this session
- facts the user just confirmed

Do not call external APIs, search the web, read Gmail, browse LinkedIn, or run
the full populate or refresh pipeline.

## Write

Update only the matched entry in place:

- For a person, edit just that row in `relationships.md`.
- For a project, edit just that project line or paragraph in `projects.md`.
- Preserve table formatting, headings, ordering, and every unrelated entry.
- Keep the change short and evidence-grounded.

## Log

Append one line to `~/context/internal/changes.md`:

```text
YYYY-MM-DD: enriched <name> — <one-line summary of what changed>
```

Create the file if it does not exist.

## Output

Confirm what changed in one sentence.
