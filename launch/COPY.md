# iContext Launch Copy Package

---

## 1. Show HN Post

**Title:**
```
Show HN: iContext – a folder + skills that give every AI agent the same brain
```

**Body:**

I built iContext because I was tired of re-explaining myself to Claude at the start of every session. "I'm building an AI app platform, I work with a team of three, here's my tech stack, here's what we decided last week..." Every single time.

The fix I wanted: Claude already knows who I am before I type anything. But I didn't want to depend on an external API or a hosted service to get there.

iContext is two things: a folder (`~/context/`) and a set of skills that your AI agents read. When you run `icontext init`, it creates the folder structure and installs skill files into `~/.claude/skills/` and `~/.cursor/rules/`. From that point on, when you open Claude Code and say "populate my icontext profile", Claude uses its own Gmail MCP and browser tools to build your profile — no external synthesis step, no API keys required.

The profile lives entirely on your machine: markdown files in three tiers (shareable, internal, vault). git-crypt encrypts the vault tier. gitleaks runs pre-commit. A doctor command tells you what's working.

Since every agent reads the same folder, Claude Code, Cursor, and Codex all start from the same shared context layer. You set it up once.

Gemini-based headless sync is also available (`pip install icontext[sync]`) for CI or no-agent setups, but it's a fallback — not the default path.

Install:
```
curl -fsSL icontext.floom.dev/install | bash
icontext init
```
Then: open Claude Code and say "Populate my icontext profile."

Repo: https://github.com/floomhq/icontext

Curious what context sources other people would want connected. Gmail and your own description are the starting points, but there's a lot more that could feed into this.

---

## 2. Twitter/X Single Launch Tweet

```
Claude Code has been asking "what are you working on?" every single session. I fixed it. icontext is a folder + skills. Your agents share a brain. Two commands, no API key: https://github.com/floomhq/icontext #buildinpublic
```

*(267 chars)*

---

## 3. Twitter/X Launch Thread

**Tweet 1 (hook):**
```
Claude Code doesn't remember you. Every session starts cold.

I got tired of re-explaining my projects, my team, and my context from scratch every morning.

So I built icontext. Thread:
```

**Tweet 2 (problem, part 1):**
```
The problem is worse than it sounds.

It's not just "Claude doesn't have context." It's that YOU have to carry that cognitive load. 

Every time: who you are, what you're building, what decisions you made last week, who you work with.

That's a tax on every session.
```

**Tweet 3 (problem, part 2):**
```
And pasting CLAUDE.md by hand only gets you so far.

Your real context is in your Gmail threads, your project docs, your own head.

Too important to leave invisible. Too sensitive to paste into every prompt.

There was no good middle ground. Until now.
```

**Tweet 4 (solution, setup):**
```
icontext is a folder and a set of skills.

Two commands:
```bash
curl -fsSL icontext.floom.dev/install | bash
icontext init
```

Then open Claude Code and say: "Populate my icontext profile."

Claude reads your Gmail via its own MCP. No external API calls. No API key needed.
```

**Tweet 5 (solution, what you get):**
```
Your agents now share a brain.

Claude Code, Cursor, and Codex all read from ~/context/ before answering.

- who you are and what you're building
- your recent decisions and relationships
- your projects, stack, and working context

Set it up once. Never explain yourself again.
```

**Tweet 6 (technical detail):**
```
Under the hood:

- Skills install into ~/.claude/skills/ and ~/.cursor/rules/
- Three-tier vault: shareable / internal / encrypted vault
- gitleaks + git-crypt block secrets before they hit git
- Gemini headless sync available as a fallback for CI/no-agent setups
- `icontext doctor --deep` tells you exactly what's working
```

**Tweet 7 (CTA):**
```
Open source.

https://github.com/floomhq/icontext

If you use Claude Code daily and re-explain yourself every session, try this. Two commands to install.

What context sources would you want connected next? (Notion, Linear, GitHub? Drop a reply)
```

---

## 4. Product Hunt Launch

**Tagline:**
```
One folder, every agent. Your AI tools now share a brain.
```
*(57 chars)*

**Description:**
```
Stop re-explaining yourself every Claude session. icontext installs a folder + skills into Claude Code, Cursor, and Codex. Your agents read from it, write to it, and keep it current — using their own tools. Local-first, no API keys, open source.
```
*(245 chars)*

**First Comment from Maker:**

Hey, I'm Federico, the builder behind iContext.

I've been running Claude Code daily for months. Every morning: new session, blank slate, re-explain the project, re-explain the team, re-explain what we decided two days ago. It's a small tax per session but it compounds badly.

I tried hand-writing CLAUDE.md files, but that's maintenance work. The real context — who I'm working with, what we're building, what decisions shaped the project — lives in my Gmail threads and in my own head. Too sensitive to paste raw, too important to leave invisible.

The solution I wanted was for the AI to figure it out itself. So that's what iContext does.

Two commands install a folder structure (`~/context/`) and a set of skill files into Claude Code and Cursor. When you ask Claude to "populate my icontext profile", it cascades through real sources on your behalf: Gmail via its own MCP, your browser if available, or a short self-description if neither works. The synthesis happens inside your Claude Code session. Nothing leaves your machine by default.

From that point, Claude Code, Cursor, and Codex all read from the same folder. One context layer. Every agent pre-loaded.

I'd love to hear what else people would want fed into their context layer.

**Topics to tag:**
- Developer Tools
- Artificial Intelligence
- Open Source
- Productivity
- Command Line

---

## 5. LinkedIn Post

I've been using Claude Code almost every day for months. There's one thing that keeps breaking the flow: every new session starts cold.

You open a terminal, you start a new chat, and Claude has no idea who you are, what you're building, who you work with, or what you decided last week. So you explain it. Again. Every time.

I got frustrated enough to build a fix.

It's called iContext. Two commands to install. No API key. When you're done, you open Claude Code and say: "Populate my icontext profile." Claude uses its own Gmail MCP to read your recent emails, figures out your projects and collaborators, and writes a structured profile to a local folder.

From that point on, every Claude Code session, every Cursor conversation, every Codex run starts pre-loaded with who you are and what you're working on. They all read from the same folder. One source of truth.

The whole thing runs locally. No server, no cloud sync. The context folder is split into three tiers based on sensitivity. A doctor command tells you exactly what's working.

Works with Claude Code, Cursor, and Codex. Two install commands:

curl -fsSL icontext.floom.dev/install | bash
icontext init

Open source, on GitHub: https://github.com/floomhq/icontext

If you use AI tools daily and you're tired of re-explaining yourself every session, this is worth five minutes.

---

## 6. Reddit Posts

### r/ClaudeAI

**Title:**
```
I built a tool that gives Claude Code persistent memory using its own skills + CLAUDE.md convention (open source)
```

**Body:**

I was losing too much time re-explaining my working context at the start of every Claude session. So I built iContext to fix it.

It works with Claude's existing skills system. Run `icontext init` and it installs skill files into `~/.claude/skills/` and writes a small `CLAUDE.md` that points at `~/context/`. From that point on, when you open Claude Code and say "Populate my icontext profile", Claude reads your Gmail via its own Gmail MCP, figures out your projects and relationships, and writes the profile itself.

No external API calls. No Gemini key. The synthesis happens inside your Claude session.

Every subsequent session, Claude reads the context folder before answering. When the profile gets stale, it offers to refresh.

Also works with Cursor (installs into `.cursor/rules/`) and Codex (via optional MCP).

Install:
```
curl -fsSL icontext.floom.dev/install | bash
icontext init
```

Repo: https://github.com/floomhq/icontext

I'd love feedback from daily Claude Code users. What context sources would you want connected next?

---

### r/LocalLLaMA

**Title:**
```
iContext: local-first context vault for AI coding agents (Claude Code, Codex, Cursor) — agent-populated, no external API by default
```

**Body:**

Built iContext to solve a problem I had: AI coding tools forget you between sessions.

The new architecture is agent-driven: `icontext init` installs skill files into `~/.claude/skills/` and `~/.cursor/rules/`. When you ask your agent to populate the profile, it uses its own tools (Gmail MCP, browser) to build it. No external API calls by default. The synthesis happens inside the agent session.

Architecture highlights for this crowd:
- No cloud sync, no hosted DB
- Three-tier vault: shareable (plaintext), internal (plaintext), vault (git-crypt encrypted)
- Local SQLite FTS index, rebuilt by git hook
- gitleaks runs pre-commit and in GitHub Actions
- `doctor --deep` verifies the full install: hooks, encryption, index, MCP, agent configs
- Headless Gemini sync still available as optional fallback for CI/no-agent setups

Currently works with Claude Code (skills + CLAUDE.md), Cursor (rules), and Codex/OpenCode (MCP).

Repo: https://github.com/floomhq/icontext

Curious whether people here are using local embedding models for retrieval. The current FTS approach works well, but semantic reranking is on the roadmap.

---

## 7. Hacker News Timing Strategy

**Best time to post:**
- Tuesday, Wednesday, or Thursday
- 8:00-9:00 AM PST (15:00-16:00 UTC)
- Avoid Mondays (too competitive) and Fridays (audience leaving for weekend)
- Aim for 8:30 AM PST for the sweet spot of early East Coast afternoon + West Coast morning

**Title pattern that works on HN:**

The "Show HN" format with a factual one-line description performs best. Avoid superlatives, avoid questions in the title, avoid implying this is unprecedented. The title above is in the right register: factual, specific, no hype.

Alternative titles if you want to test:
- "Show HN: iContext – open-source context vault for AI coding agents, agent-populated"
- "Show HN: iContext – skills + folder that give Claude Code persistent memory"

**First 2 hours:**

1. Post and walk away for 20 minutes. Don't refresh obsessively.
2. Reply to every comment within the first hour, even short ones. HN rewards engagement and the algo factors it.
3. Clarify technical details directly. HN readers want specifics: how the skills system works, how git-crypt is implemented, what data the Gmail MCP accesses.
4. If someone finds a bug or gap, acknowledge it immediately and open a GitHub issue in real time. Link the issue in your reply. This signals you're serious.
5. Share the HN link on Twitter/X and LinkedIn only AFTER it has 5+ upvotes to avoid looking like you're brigading.

**How to handle negative comments:**

- Assume good faith. Most HN criticism is genuine.
- For "why not just use CLAUDE.md": explain that iContext creates the folder structure, installs skills, handles encryption and secret scanning, and works across multiple agents. That's a different scope.
- For "why does it need Gmail access": the Gmail MCP access is scoped to metadata (subjects, senders). No message bodies leave the agent session. The user controls which MCP tools their agent can use.
- For "this is a security risk": the doctor command and three-tier vault system exist specifically for this concern. Link to the SECURITY.md.
- Never be defensive. HN can smell it. "That's a fair concern, here's how I thought about it" always lands better than "actually this is not a problem because..."

---

## 8. Viral Hooks Bank

Ranked roughly by virality potential (1 = most shareable):

1. **"Claude Code has been asking 'what are you working on?' at the start of every session. I fixed it."**

2. **"Your AI agents don't share a brain. They should. Two commands to fix that."**

3. **"icontext is a folder. Your AI agents read it, write to it, and keep it current. That's the whole product."**

4. **"The missing layer between your private context and your AI tools: a local folder with skills."**

5. **"CLAUDE.md is a hand-written lie. icontext builds your context from real data, using your agent's own tools."**

6. **"After icontext: open Claude, ask 'what do you know about me?' and it already knows."**

7. **"Every AI coding tool has the same cold-start problem. One folder + skills fixes all of them at once."**

8. **"Your AI can already read your Gmail. I just built the convention so it writes the results somewhere useful."**

9. **"No API key. No server. Your agent populates its own context. That's the whole install."**

10. **"Persistent memory for Claude Code, Cursor, and Codex. Local. Encrypted. Open source. Two commands."**
