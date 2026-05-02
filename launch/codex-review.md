# iContext Synthesis Pipeline — Codex Review
*Model: gpt-5.5 | Date: 2026-05-02 | Tokens used: Pass 1 ~59K, Pass 2 ~50K*

---

## PASS 1: Synthesis Pipeline Review

### Findings (12 concrete issues, with file:line references)

**1. `connectors/gmail.py:60` — CC hallucination**
Prompt asks Gemini to infer "CC patterns / decision-making signals" but `_fetch_folder` at line 148 only fetches `SUBJECT FROM TO DATE`. There is no CC data. This forces the model to hallucinate.
Fix: either add `CC` to the IMAP `BODY.PEEK[HEADER.FIELDS ...]` fetch and surface it in `_build_summary`, or remove the Decision-Making Signals prompt section and replace with `Unknown: no CC metadata collected`.

**2. `connectors/gmail.py:198` — direction conflation produces fake relationships**
`_build_summary` counts every `To:` address as "recipients you sent to," including inbox messages. Since `sync()` at line 397 merges inbox and sent without tagging direction, inbound newsletter recipients appear as real outbound relationships.
Fix: tag records with `direction: inbox|sent` in `_fetch_folder`; count outbound recipients only from Sent folder records, inbound senders only from Inbox records.

**3. `connectors/gmail.py:199` — comma-split corrupts display names**
`to_raw.split(",")` corrupts valid RFC 2822 display names like `"Doe, Jane" <jane@example.com>`, producing bogus recipients such as `doe`.
Fix: replace with `email.utils.getaddresses([to_raw])` — stdlib, no dependency.

**4. `connectors/gmail.py:157` — line-by-line header parser drops folded continuations**
The manual `line.lower().startswith("subject:")` parser drops RFC 2822 folded header continuations (lines starting with whitespace). Folded subjects get truncated; folded `To:` fields lose secondary recipients entirely.
Fix: parse raw header bytes with `email.parser.BytesParser(policy=email.policy.default)` and read `msg["subject"]`, `msg["from"]`, `msg["to"]`, `msg["cc"]` directly.

**5. `connectors/gmail.py:210` — sent subjects starved by inbox-first ordering**
`subjects[:150]` takes the first 150 subjects, but line 390 appends inbox messages before sent. A busy inbox (300 messages) excludes all sent subjects, making the profile inbox-only in tone.
Fix: parse dates from all records, sort descending by date, then sample subjects bounded by direction and account; additionally surface top repeated normalized thread subjects separately.

**6. `connectors/gmail.py:422` and `connectors/linkedin.py:184` — hard char truncation mid-stream**
Both connectors hard-truncate input to 8,000 characters without token awareness. This can cut a relationship table mid-row, cut LinkedIn's Education or Skills sections, or — critically — cut the prompt instructions for the `<!-- SECTION -->` delimiters themselves, causing silent section-extraction failures downstream.
Fix: use token counting (the Gemini SDK exposes `count_tokens`), chunk by logical section, and run a reduce-stage synthesis from structured intermediate facts rather than one truncated blob.

**7. `connectors/base.py:115` — no retry, no timeout, no error classification**
`gemini_synthesize` calls `model.generate_content(prompt)` with no request timeout, no retry on 429/503, no finish-reason inspection, and no safety-block handling. A rate limit raises a raw SDK exception; a safety block causes `response.text` to raise `ValueError` with a confusing traceback rather than an actionable message.
Fix: wrap in a helper with configurable `request_options={"timeout": 60}`, exponential backoff with jitter for 429/503, explicit check of `response.candidates[0].finish_reason`, and a clear `RuntimeError` if blocked/empty.

**8. `connectors/linkedin.py:190` — missing emptiness guard**
LinkedIn's `sync()` writes `gemini_output` unconditionally; Gmail added an emptiness guard at line 430 but LinkedIn never received the same fix.
Fix: centralize response validation inside `gemini_synthesize` or a `synthesize_required()` wrapper so both connectors benefit. Also validate required sections are present before writing any profile file.

**9. `connectors/gmail.py:31` — prompt over-claims on thin evidence**
`_SYNTHESIS_PROMPT` asks for identity, projects, warmth inferences, pending items, and decision-making from only sender counts + 150 subject snippets. With no body text, no dates on specific events, and no CC data, the model produces generic outputs ("You seem to be a busy professional working on multiple initiatives") because there is no evidence field anchoring each claim.
Fix: restructure the prompt to require `claim | evidence | confidence` triplets; mandate `Unknown [no evidence]` when a field cannot be grounded; include normalized subject clusters with counts and recent dated examples so the model has real signal.

**10. `connectors/gmail.py:234` — fragile HTML-comment section extraction, silent failures**
`_extract_section` relies on the model faithfully reproducing `<!-- SECTION: relationships -->` and `<!-- END SECTION -->` exactly. When Gemini omits, reformats, or wraps these markers in a code block, `_extract_section` returns `""` and lines 459/466 silently skip writing `relationships.md` and `projects.md` with no error or warning.
Fix: use structured JSON output (`response_mime_type: "application/json"`) for machine-owned fields. Parse output into a typed schema. Render `user.md`, `relationships.md`, `projects.md`, `context-card.md` deterministically from JSON fields. Fail sync — do not silently skip — if required JSON fields are absent.

**11. `connectors/gmail.py:485` — inline card prompt, privacy leak risk**
The context-card prompt is built inline (not as a testable `_CARD_PROMPT` constant) and feeds the full private profile including relationship names and email patterns into a second free-form Gemini call. The instruction "no private relationship details" is advisory; the model can and does echo names from the profile into the card.
Fix: promote to a named `_CARD_PROMPT` constant. Generate the card from an allowlisted public-schema JSON (identity + projects only, no `relationships` field). Validate that card output contains no email addresses and no names that appear only in the private `relationships` section.

**12. `connectors/base.py:73–84` — per-file commits swallow all errors**
`write_profile` commits after every single file write and swallows all `CalledProcessError` silently (`pass`). A git hook failure, missing git config, or corrupt index leaves the vault with partial files (some committed, some not) with zero signal to the user.
Fix: collect all file writes first, then stage once (`git add -A`) and commit once. Distinguish "nothing to commit" (acceptable, ignore) from all other errors (surface as a warning with the git stderr).

---

**Codex verdict on structured outputs vs free-form:**
> Structured outputs (JSON schema) would definitively beat free-form Markdown here. The repo requires deterministic modular files and validation. A single missed marker currently silently drops a whole profile section. Multi-stage synthesis (extract → validate → synthesize) would also beat the current single-stage call.

---

## PASS 2: Alternative Implementation Spec

**Spec: Structured Synthesis Flow**

### Stage 0: Local fact normalization

Gmail emits compact, deterministic records per message:
`id, direction, date_week, counterparty_email, counterparty_name?, domain, subject_clean, thread_key, account_label`

Strip: Re/Fwd prefixes, mailing-list markers, bot addresses, tracking subjects, own addresses. Keep: top counterparties, top domains, active threads, sampled subjects per cluster.

### Stage A: Entity extraction (Gemini JSON mode)

Send compact Gmail facts + LinkedIn facts to Gemini with structured output. Output schema:

```
people[]        — name, email, domain, confidence, source_ids[], counts, last_seen, rationale
companies[]     — name, domain, confidence, source_ids[]
projects[]      — name, participants[], evidence_subjects[], confidence
topics[]        — name, frequency, recent_example
evidence[]      — id, date, direction, counterparty, subject_normalized
```

Every entity includes `confidence`, `source_ids` (linking back to evidence records), `counts`, `last_seen`, and `rationale`.

### Stage B: Local validation (no Gemini call)

- Validate JSON with Pydantic; reject entities without evidence IDs
- Merge duplicates by email/domain/name similarity
- Compute hard metrics locally: messages/week, inbound/outbound ratio, last contact date, top co-participants
- This stage runs entirely offline — no additional token cost

### Stage C: Profile synthesis (Gemini JSON mode)

Send only validated entities + computed metrics to Gemini. Output structured sections:
`identity_summary`, `relationships_markdown`, `projects_markdown`, `topics`, `communication_patterns`, `pending_watch`, `shareable_card`

Markdown files are rendered deterministically from JSON fields. No HTML comment parsing.

### Evidence grounding mechanism

Each claim in the output carries:
```json
{
  "claim": "Cedrik is a high-frequency collaborator",
  "evidence": ["gmail:c42"],
  "metric": "12 messages / 4 weeks, 3.0 per week, last seen 2026-04-30"
}
```
Final prose: "You email Cedrik about 3x/week" — only when the validator confirms the count. Low-confidence claims render with `[?]` or are omitted entirely.

### Gemini API features to use

- `response_mime_type: "application/json"` + `response_json_schema` (current Gemini API)
- Or `response_schema` with typed SDK models (where supported by google-genai SDK)
- **Do NOT use function calling** — function calling is for model-triggered external actions. This pipeline needs structured final output, which is what JSON mode is for.
- Source: https://ai.google.dev/gemini-api/docs/structured-output

### Migration plan

**`base.py`:** Replace `gemini_synthesize(prompt) -> str` with `gemini_generate(prompt, schema, model) -> dict`. Add JSON parsing, Pydantic schema validation, retry-on-invalid-JSON, configurable timeout, and SDK migration path from deprecated `google-generativeai` to `google-genai`.

**`gmail.py`:** Replace `_build_summary` with compact fact extraction + clustering + evidence ID assignment + bot filtering + metric computation. Two Gemini calls: Stage A entity extraction, Stage C profile synthesis. Remove `_extract_section` entirely. Remove inline card prompt; card is a JSON field from Stage C.

**`linkedin.py`:** Convert PDF text into structured facts first (roles, companies, skills, education), then feed the same entity schema used by Gmail. Reuse LinkedIn as grounding for roles/companies; Gmail as grounding for active relationships/projects. Single Gemini call for extraction + synthesis.

### Token budget analysis

| Path | Input tokens | Output tokens | Notes |
|------|-------------|---------------|-------|
| Gmail current | ~2,000 | ~1,000 + card | 8K char hard truncation, no structure |
| Gmail Stage A (new) | ~1,500–2,500 | ~800 | Compact facts, clustered |
| Gmail Stage C (new) | ~1,000–1,800 | ~1,200 | Validated entities only |
| LinkedIn current | ~2,000 | ~800 | 8K char hard truncation |
| LinkedIn new | ~1,200–1,800 | ~600 | Structured PDF sections only |

Net token cost is roughly equivalent or slightly higher due to two calls, but quality is dramatically higher and output is deterministic.

---

## Top 3 Improvements to Implement

Based on Codex's findings, ranked by impact-to-effort ratio:

### 1. Direction-tagged records + `email.utils.getaddresses` (findings #2, #3, #4)
**Impact: High. Effort: Low.**
Three stdlib-only fixes that eliminate fabricated relationships from the relationship table — the single most visible quality problem. Tag inbox/sent records in `_fetch_folder`, use `email.utils.getaddresses` for `To:` parsing, use `BytesParser` for header parsing. No new dependencies.

### 2. Structured JSON output replacing HTML comment section extraction (finding #10)
**Impact: High. Effort: Medium.**
Replace `_extract_section` + `<!-- SECTION -->` markers with `response_mime_type: "application/json"` + a typed schema. This eliminates silent partial-profile drops, makes output deterministic, and is the prerequisite for all quality improvements downstream. Requires adding Pydantic or manual schema validation.

### 3. Gemini error handling: retry + timeout + finish-reason guard (finding #7)
**Impact: Medium. Effort: Low.**
A 10-line wrapper around `generate_content` that adds `request_options={"timeout": 60}`, exponential backoff for 429/503, and explicit `finish_reason` / `safety_ratings` checks. Prevents the most common production failures (rate limits during first sync, safety-blocked profiles) from surfacing as cryptic SDK tracebacks.

---

*Codex did not modify any files. All 45 tests passed before and after the review.*
