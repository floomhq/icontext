# Contributing

Thanks for your interest in iContext.

## Reporting issues

- **Bugs**: file a GitHub issue with steps to reproduce, your OS, Python version
- **Feature requests**: open an issue with the use case (not just the feature)
- **Security**: email security@floom.dev, do not file public issues

## Pull requests

1. Fork and create a feature branch
2. Add tests for new behavior — see `tests/`
3. Run `python3 -m pytest tests/ -x` and `python3 -m py_compile cli.py connectors/*.py`
4. Run `python3 scripts/doctor.py --repo .` to confirm install integrity
5. Open a PR with a clear description

## Local development

```bash
git clone https://github.com/floomhq/icontext ~/icontext-dev
cd ~/icontext-dev
pip install -e .
pip install pytest
pytest tests/
```

## Connectors

Want to add a new data source (Calendar, Notion, etc.)? Subclass `BaseConnector` in `connectors/your_source.py`. Implement `connect()`, `sync()`, `status()`. Register in cli.py's `_get_connector()`.

## Design rules

- Keep the default path local-first and offline.
- Keep secrets and private vault data out of fixtures, docs, logs, and tests.
- Prefer deterministic checks over LLM calls for safety gates.
- Add integrations only for agents that are verified with a real CLI or config path.
- Keep public docs generic; personal examples belong in private vault eval files.

## License

MIT — see [LICENSE](LICENSE).
