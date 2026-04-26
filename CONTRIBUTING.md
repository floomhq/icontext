# Contributing

`icontext` is intentionally small. Contributions are welcome when they improve
the local vault workflow without adding hosted dependencies, broad agent
frameworks, or hidden runtime cost.

## Development

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
gitleaks detect --config config/gitleaks.toml --redact --no-banner
```

## Design Rules

- Keep the default path local-first and offline.
- Keep secrets and private vault data out of fixtures, docs, logs, and tests.
- Prefer deterministic checks over LLM calls for safety gates.
- Add integrations only for agents that are verified with a real CLI or config
  path.
- Keep public docs generic; Federico-specific examples belong in private vault
  eval files.

## Pull Requests

Include:

- The problem being solved.
- The verification command output.
- Any change to hook behavior, MCP tool behavior, or config file formats.

Security-sensitive changes need extra care. Open a private security report for
anything involving secret leakage, encryption, or prompt-context exposure.
