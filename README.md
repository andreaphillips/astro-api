# astro-api

Stateless HTTP API exposing Western astrology calculations (natal charts, transits, synastry, current sky) via the Swiss Ephemeris. Designed to be consumed by an LLM client (Claude, ChatGPT) through Delegate's auto-generated MCP tools.

See `docs/superpowers/specs/2026-04-26-astro-api-design.md` for the full design spec.

## Local development

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn astro_api.main:app --reload
curl http://127.0.0.1:8000/healthz
```

## Tests and lint

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
```
