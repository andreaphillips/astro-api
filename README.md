# astro-api

Stateless HTTP API exposing Western astrology calculations (natal charts, transits, synastry, composite charts, current sky) via the Swiss Ephemeris. Designed to be consumed by an LLM client (Claude, ChatGPT) through Delegate's auto-generated MCP tools.

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

## Running your own instance

This repository is the source; the deployment at any given URL is not shared.
Every `/v1/*` endpoint requires an `X-API-Key` header matching the server's
`ASTRO_API_KEY`, so to use this API you run your own copy:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # paste into ASTRO_API_KEY
uv sync && uv run uvicorn astro_api.main:app
```

Deploy it wherever you like — Railway, Fly, Render, a VPS, Docker (see
`Dockerfile`). Set `ASTRO_API_KEY` and `PUBLIC_BASE_URL` in that environment.
The key must be at least 32 characters; the app refuses to start otherwise.

## License

Copyright (C) 2026 Andrea Phillips.

Licensed under the GNU Affero General Public License, version 3 or later
(AGPL-3.0-or-later). See [LICENSE](LICENSE) for the full text.

The AGPL applies because this project builds on
[Immanuel](https://github.com/theriftlab/immanuel-python) and
[pyswisseph](https://github.com/astrorigin/pyswisseph), both AGPL-3.0. Under
section 13, anyone who runs a modified version of this software as a network
service must offer its complete source to the users of that service.

Source: https://github.com/andreaphillips/astro-api

The Swiss Ephemeris itself is dual-licensed; a commercial license is available
from [Astrodienst](https://www.astro.com/swisseph/) if AGPL terms do not suit
your deployment.
