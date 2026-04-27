# Astro API — Design Spec

**Date:** 2026-04-26
**Author:** Andrea Phillips
**Status:** Approved for implementation
**Project folder:** `~/Work/astro-api/`

---

## 1. Purpose

Build a small, stateless HTTP API that exposes Western astrology calculations (natal charts, transits, synastry, current sky) computed via the Swiss Ephemeris. The API is consumed by an LLM client (Claude Code, Claude Desktop, ChatGPT) through Delegate, which auto-generates MCP tools from the API's OpenAPI spec. The LLM handles all interpretation and narrative; this service produces structured data only.

Use case: personal and family use — "give me my mom's natal chart", "how compatible am I with my sister", "what transits are hitting me today". Internal tool, not a public product.

## 2. Audience & Constraints

- **Users:** Andrea + family. Maybe ~5 people total. Internal sharing only.
- **Auth:** single shared secret via `X-API-Key` header. No multi-user, no accounts.
- **Persistence:** **none.** Memory of birth data lives in the LLM layer (Claude memory, ChatGPT memory, Megabrain). The API is pure compute.
- **Hosting:** Railway, Hobby plan ($5/mo expected to be plenty).
- **Output language:** English (`en_US` — Immanuel default). The LLM client handles any user-facing translation.
- **Scale:** trivial — handful of requests per day.

## 3. Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Required by Immanuel; Andrea is Python-fluent |
| Web framework | FastAPI | Auto-generates OpenAPI spec for Delegate |
| Astrology engine | [Immanuel](https://github.com/theriftlab/immanuel-python) | Built on Swiss Ephemeris, JSON serializer included, native `es_ES` locale |
| Geocoding | `geopy` + Nominatim (OpenStreetMap) | Free, no key needed, must set User-Agent |
| Timezone resolution | `timezonefinder` | Offline lat/lon → IANA tz |
| Settings | `pydantic-settings` | Env-driven config |
| Dep manager | `uv` | Fast, modern, lockfile |
| Lint/format | `ruff` | One binary for both |
| Tests | `pytest` | Standard, with snapshot fixtures |
| Container | Docker (`python:3.11-slim`) | Predictable runtime; Railway respects Dockerfile |
| Hosting | Railway | Auto-deploy on `git push`, free TLS, PORT injection |
| MCP layer | Delegate (`add_service_from_spec`) | Ingests OpenAPI → exposes MCP tools |

**Out of scope dependencies:** no Redis, no Postgres, no message queue, no Prometheus.

## 4. API Endpoints

All endpoints under `/v1`. All authenticated except `/healthz` and `/openapi.json`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/natal` | Compute a full natal chart for one subject |
| `POST` | `/v1/transits` | Compute transits to a natal chart at a target date |
| `POST` | `/v1/synastry` | Compare two natal charts (cross-aspects + composite metrics) |
| `GET` | `/v1/sky` | Current planetary positions (or at a given datetime) |
| `GET` | `/healthz` | Liveness probe for Railway. No auth. |
| `GET` | `/openapi.json` | OpenAPI 3.1 spec for Delegate ingestion. No auth. |

**Phase 2 (not in this spec, planned next iteration):**
- `POST /v1/solar-return` — solar return chart for a given year
- `POST /v1/progressions` — secondary progressions

## 5. Data Shapes

> JSON examples below are illustrative; the canonical schema is the Pydantic models in `src/astro_api/schemas.py` and the resulting `/openapi.json`. Field names, casing, and nesting must match the examples.

**Aspects computed:** the five major aspects only — conjunction, opposition, trine, square, sextile. No minor aspects (quincunx, semi-square, etc.) in v1. Default orbs follow Immanuel's defaults; do not override.

### 5.1 Shared `Subject` input

```json
{
  "name": "Andrea",
  "birth_date": "1989-05-12",
  "birth_time": "14:30",
  "birth_place": "Maracaibo, Venezuela"
}
```

- `name` — optional, used only to label the response.
- `birth_date` — ISO 8601 date, required.
- `birth_time` — `HH:MM` 24-hour, **optional**. If omitted, the chart is computed at 12:00 local time (noon-chart convention) and `houses`, `angles`, and `points.part_of_fortune` are returned as `null`; the response includes warning code `birth_time_unknown`. Note that without an exact time the Moon can drift up to ~6.5° from its true birth position.
- `birth_place` — free-text string. The server geocodes via Nominatim and resolves timezone via timezonefinder.

### 5.2 `/v1/natal` request and response

**Request:**

```json
{
  "subject": { ...Subject },
  "house_system": "placidus"   // optional, default: placidus
}
```

Allowed `house_system`: `placidus`, `whole_sign`, `koch`, `equal`.

**Response:**

```json
{
  "subject": {
    "name": "Andrea",
    "datetime_utc": "1989-05-12T18:30:00Z",
    "latitude": 10.66,
    "longitude": -71.65,
    "timezone": "America/Caracas"
  },
  "house_system": "placidus",
  "planets": {
    "sun":     { "sign": "taurus", "degree": 21.83, "house": 7, "retrograde": false,
                 "dignity": "neutral", "weight": 4.2 },
    "moon":    { "sign": "leo",    "degree": 4.21,  "house": 10, "retrograde": false,
                 "dignity": "peregrine", "weight": 2.1 }
    // Same shape repeated for: mercury, venus, mars, jupiter, saturn,
    // uranus, neptune, pluto, chiron
  },
  "points": {
    // Each point uses the shape:
    //   { "sign": <string>, "degree": <float>, "house": <int>, "retrograde": <bool|null> }
    // `retrograde` is null for points where direction is not a meaningful
    // concept (vertex, part_of_fortune).
    "north_node":      { },   // true node
    "south_node":      { },   // true node
    "lilith":          { },   // Black Moon Lilith (mean)
    "vertex":          { },
    "part_of_fortune": { }
  },
  "angles": {
    "ascendant": { "sign": "scorpio",  "degree": 12.4 },
    "midheaven": { "sign": "leo",      "degree": 23.1 },
    "descendant":{ "sign": "taurus",   "degree": 12.4 },
    "imum_coeli":{ "sign": "aquarius", "degree": 23.1 }
  },
  "houses": [
    { "number": 1, "sign": "scorpio", "cusp_degree": 12.4 }
    // 12 entries total, one per house, ordered 1 → 12
  ],
  "aspects": [
    { "from": "sun", "to": "moon", "type": "trine", "orb": 1.4, "applying": true }
    // One entry per detected aspect, sorted by orb ascending
  ],
  "warnings": []
}
```

**Field semantics:**

- `dignity`: one of `domicile`, `exaltation`, `detriment`, `fall`, `peregrine`, `neutral`. Comes from Immanuel.
- `weight`: essential dignity score from Immanuel (numeric, scale defined by Immanuel docs). Higher = stronger placement. Useful for highlighting "loud" planets.
- `applying`: `true` if the aspect is forming (planets moving toward exact), `false` if separating.
- Nodes are computed as **true nodes** (not mean) so `points.north_node.retrograde` and `points.south_node.retrograde` carry real information — true nodes can briefly turn direct, mean nodes are always retrograde by construction.
- `orb`: absolute degrees of separation from exact aspect.
- Sign names, aspect names, and dignity labels are returned in English (`taurus`, `leo`, `trine`, `square`, `domicile`, etc.) per the `DEFAULT_LOCALE=en_US` setting.
- `warnings` is always present, possibly empty. Known warning codes: `multiple_matches` (geocoding ambiguity), `birth_time_unknown` (no `birth_time` provided; chart computed at noon local time with `houses`, `angles`, and `points.part_of_fortune` set to `null`).

### 5.3 `/v1/transits` request

```json
{
  "natal_subject": { ...Subject },
  "target_date": "2026-04-26T12:00:00Z"   // optional, default: now (UTC)
}
```

Response: same envelope as natal, but with an additional `transits` block listing aspects from the current sky's planets to the natal planets, sorted by orb.

### 5.4 `/v1/synastry` request

```json
{
  "subject_a": { ...Subject },
  "subject_b": { ...Subject }
}
```

Response: each chart returned in full, plus a `synastry` block:

```json
"synastry": {
  "cross_aspects": [
    { "from_a": "sun", "to_b": "moon", "type": "trine", "orb": 2.1, "applying": true }
    // One entry per A→B aspect detected, sorted by orb ascending.
    // The LLM client formats human-readable summaries; the API returns
    // structured data only.
  ]
}
```

### 5.5 `/v1/sky` request

`GET /v1/sky?date_time=2026-04-26T12:00:00Z` (query string, optional, default: now).

Response: planets + points + angles for the given UTC datetime, no houses (no location).

## 6. Defaults & Configuration

Loaded via `pydantic-settings` from environment variables:

```bash
# Auth
ASTRO_API_KEY=                                      # required, shared secret

# Geocoding
NOMINATIM_USER_AGENT=astro-api/1.0 (aphillipsr@gmail.com)
NOMINATIM_TIMEOUT_SECONDS=5

# Astrology defaults
DEFAULT_HOUSE_SYSTEM=placidus                       # placidus|whole_sign|koch|equal
DEFAULT_LOCALE=en_US

# Server
PORT=8000                                           # Railway injects
LOG_LEVEL=info
```

**Geocoding cache:** in-process `functools.lru_cache(maxsize=512)` keyed by normalized `birth_place` string. Lost on container restart — acceptable; geocoding is cheap and the family pool is tiny.

## 7. Error Handling

All errors return JSON: `{ "error": "<code>", "detail": "<human message>" }`.

| Condition | HTTP | Code |
|---|---|---|
| Missing or invalid `X-API-Key` | 401 | `unauthorized` |
| `birth_place` not found in Nominatim | 422 | `place_not_found` |
| `birth_place` ambiguous (multiple results) | 200 | (success, with `warnings: ["multiple_matches"]`) |
| `birth_time` missing | 200 | (success, with `warnings: ["birth_time_unknown"]`; chart computed at noon, `houses`/`angles`/`points.part_of_fortune` null) |
| Date outside ephemeris range | 422 | `date_out_of_range` |
| Nominatim timeout | 503 | `geocoding_unavailable` |
| Unhandled server error | 500 | `internal_error` |

Validation failures from Pydantic surface as 422 with FastAPI's default error envelope (acceptable, no need to override).

**Logging:** structured JSON to stdout, captured by Railway. Log every request with method, path, status, latency_ms, and (on errors) the error code. Never log the API key or full geocoded address with PII beyond what was already in the request.

## 8. Project Structure

```
~/Work/astro-api/
├── README.md
├── pyproject.toml              # uv-managed deps
├── uv.lock
├── .env.example
├── .gitignore
├── Dockerfile
├── railway.json
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-26-astro-api-design.md   # this file
├── src/
│   └── astro_api/
│       ├── __init__.py
│       ├── main.py             # FastAPI app, includes routers, mounts /healthz
│       ├── auth.py             # X-API-Key dependency
│       ├── geocoding.py        # Nominatim wrapper + timezonefinder + lru_cache
│       ├── charts.py           # thin wrappers over Immanuel: build_natal, build_transits, build_synastry, build_sky
│       ├── schemas.py          # Pydantic: Subject, NatalRequest, NatalResponse, etc.
│       └── settings.py         # pydantic-settings
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_geocoding.py
    ├── test_natal.py
    ├── test_transits.py
    ├── test_synastry.py
    ├── test_sky.py
    └── fixtures/
        └── known_charts.json   # reference charts validated once against astro.com, snapshotted
```

**Module responsibilities (one purpose each):**

- `auth.py` — single function `require_api_key` used as FastAPI dependency.
- `geocoding.py` — single function `resolve_place(place: str) -> ResolvedLocation` that returns `(lat, lon, tz)`. Caches in-process. Raises typed exceptions for not_found / ambiguous / timeout.
- `charts.py` — pure functions taking resolved Subject + parameters, returning Pydantic response models. No HTTP, no env access.
- `schemas.py` — all Pydantic models. No business logic.
- `main.py` — wires routers, registers exception handlers, returns OpenAPI metadata.

## 9. Deployment

**Dockerfile** (sketch):

```dockerfile
FROM python:3.11-slim
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src ./src
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "uv run uvicorn astro_api.main:app --host 0.0.0.0 --port $PORT"]
```

**railway.json:**

```json
{
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "healthcheckPath": "/healthz",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE"
  }
}
```

**Deploy flow:**

1. Push to `main` → Railway builds and deploys.
2. Railway provides public URL (e.g., `https://astro-api-production.up.railway.app`).
3. Set `ASTRO_API_KEY` in Railway env (generate via `openssl rand -hex 32`).
4. From Andrea's Claude session, call Delegate `add_service_from_spec` with the OpenAPI URL and the `X-API-Key` header. Delegate exposes MCP tools.
5. Family members repeat step 4 in their own Claude Desktop with the same key.

## 10. Out of Scope (YAGNI)

Not building, not designing, not stubbing:

- Persistence of any kind (DB, Redis, file storage).
- User accounts, multi-tenancy, per-user rate limits.
- Custom MCP server code — Delegate covers it via OpenAPI.
- Solar returns, secondary progressions (planned phase 2).
- Vedic / sidereal calculations.
- Asteroid belt beyond Chiron.
- Interpretation/narrative — that lives in the LLM client.
- Frontend / web UI.
- CI/CD pipelines beyond Railway's auto-deploy.
- Observability platforms (Datadog, Sentry). Stdout JSON logs are enough.
- Retry logic against Nominatim. One attempt, fail clean, let the LLM retry if needed.

## 11. Acceptance Criteria

The spec is satisfied when:

1. `git push` to a fresh Railway service deploys the API and `/healthz` returns 200.
2. `GET /openapi.json` returns a valid OpenAPI 3.1 document including all four `/v1/*` endpoints with `X-API-Key` security defined.
3. `POST /v1/natal` with a valid Subject returns a complete chart (planets, points, angles, houses, aspects) in under 1 second p95.
4. `POST /v1/synastry` with two Subjects returns both charts plus cross-aspects.
5. `POST /v1/transits` returns transits for the requested target date (or now if omitted).
6. `GET /v1/sky` returns current planetary positions.
7. Missing or wrong `X-API-Key` returns 401 on all `/v1/*` endpoints.
8. Unknown `birth_place` returns 422 with `place_not_found`.
9. Missing `birth_time` returns 200 with the chart computed at noon local time, `warnings: ["birth_time_unknown"]`, and `houses`, `angles`, and `points.part_of_fortune` set to `null`.
10. A known reference chart (e.g., a public figure with documented natal data) matches astro.com within ±0.05° on all major planets — captured as a snapshot test in `tests/fixtures/known_charts.json`.
11. Delegate's `add_service_from_spec` against the deployed URL successfully exposes all four endpoints as MCP tools, and a follow-up LLM call (e.g., "carta natal de Andrea, 12 de mayo de 1989, 14:30, Maracaibo") returns structured chart data.

## 12. Open Questions

None at spec time. Phase-2 features (solar return, progressions) get their own spec when prioritized.
