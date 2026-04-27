# Astro API — Phase 2: Solar Return + Progressions

**Date:** 2026-04-27
**Author:** Andrea Phillips
**Status:** Approved for implementation
**Builds on:** [Phase 1 spec](./2026-04-26-astro-api-design.md) — same stack, conventions, auth, deploy. Read that first.

---

## 1. Purpose

Add two derived-chart endpoints to the existing astro-api:

- **Solar return** — chart cast for the moment the natal Sun returns to its birth position in a given year. Optional relocation.
- **Secondary progressions** — symbolic technique (1 day = 1 year). Returns progressed positions plus aspects from progressed planets to the natal chart.

After deploy, re-run Delegate's `add_service_from_spec` so the new MCP tools surface in the LLM clients (5 → 7 tools).

## 2. Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/solar-return` | Solar return chart for a given year |
| `POST` | `/v1/progressions` | Secondary progressions to a target date |

Both authenticated via `X-API-Key`. Both under `/v1/`.

Both **require** `birth_time` — no noon-fallback. SR depends on the exact natal Sun degree which needs exact natal time; progressed Moon at age 35 with a noon-fallback could be off by ~13° (a full sign).

## 3. `/v1/solar-return`

### Request

```json
{
  "subject": { ...Subject },
  "year": 2026,
  "relocation_place": "Tamarindo, Costa Rica",
  "house_system": "placidus"
}
```

- `subject` — required. Phase 1 `Subject`. `birth_time` required.
- `year` — required integer (e.g. 2026). Outside ephemeris bounds → 422 `date_out_of_range`.
- `relocation_place` — optional free-text place. If provided, the SR chart is cast at the relocated location (geocoded via Nominatim). Standard "travel for your solar return" technique.
- `house_system` — optional, default = `settings.DEFAULT_HOUSE_SYSTEM`.

### Response

```json
{
  "subject": {
    "name": "Andrea",
    "datetime_utc": "1980-12-09T10:35:00Z",
    "latitude": 9.93, "longitude": -84.08, "timezone": "America/Costa_Rica"
  },
  "return_moment": {
    "datetime_utc": "2026-12-09T07:42:13Z",
    "latitude": 10.30, "longitude": -85.84, "timezone": "America/Costa_Rica"
  },
  "relocated": true,
  "house_system": "placidus",
  "planets": { ... },
  "points": { ... },
  "angles": { ... },
  "houses": [ ... ],
  "aspects": [ ... ],
  "warnings": []
}
```

- `subject` — resolved natal data (for cross-reference).
- `return_moment` — exact UTC instant of the SR + the location at which the chart was cast (birthplace if no relocation, else the relocated coords).
- `relocated` — `true` iff `relocation_place` was provided.
- The rest mirrors `/v1/natal` (planets, points with retrograde, angles, 12 houses, 5-major aspects sorted by orb).

### Errors

| Condition | HTTP | Code |
|---|---|---|
| `birth_time` missing | 422 | `birth_time_required_for_solar_return` |
| `year` outside ephemeris range | 422 | `date_out_of_range` |
| `birth_place` not found | 422 | `place_not_found` |
| `relocation_place` not found | 422 | `place_not_found` |
| `birth_place` ambiguous | 200 | success + `warnings: ["multiple_matches"]` |

## 4. `/v1/progressions`

### Request

```json
{
  "subject": { ...Subject },
  "target_date": "2026-04-27",
  "house_system": "placidus"
}
```

- `subject` — required. `birth_time` required.
- `target_date` — optional ISO date `YYYY-MM-DD`, default = today UTC. Secondary progressions: 1 day = 1 year of life.
- `house_system` — optional, default = `settings.DEFAULT_HOUSE_SYSTEM`.

### Response

```json
{
  "subject": { ...ResolvedSubject },
  "target_date": "2026-04-27",
  "progressed_datetime_utc": "1981-02-12T19:03:54Z",
  "house_system": "placidus",
  "natal": {
    "planets": { ... },
    "points": { ... },
    "angles": { ... },
    "houses": [ ... ]
  },
  "progressed": {
    "planets": { ... },
    "points": { ... },
    "angles": { ... }
  },
  "progressed_aspects": [
    { "from": "moon", "to": "venus", "type": "trine", "orb": 1.2, "applying": true }
  ],
  "warnings": []
}
```

- `progressed_datetime_utc` — actual UTC instant in the natal year mapping to `target_date` (`birth_datetime + (target_date - birth_date)` days).
- `natal` — natal positions, used for cross-reference and to compute aspects.
- `progressed` — progressed positions at `progressed_datetime_utc`. **No `houses`** in the progressed block (progressions don't move houses in the standard interpretation; the natal houses are the reference frame).
- `progressed_aspects` — aspects from progressed planets to natal planets, 5 majors only, sorted by orb ascending. `from` = progressed body, `to` = natal body.

### Errors

| Condition | HTTP | Code |
|---|---|---|
| `birth_time` missing | 422 | `birth_time_required_for_progressions` |
| Derived progressed datetime out of ephemeris | 422 | `date_out_of_range` |
| `birth_place` not found | 422 | `place_not_found` |
| `birth_place` ambiguous | 200 | success + `warnings: ["multiple_matches"]` |

## 5. Schema additions

In `src/astro_api/schemas.py`, add:

- `SolarReturnRequest`, `SolarReturnResponse`
- `ProgressionsRequest`, `ProgressionsResponse`
- `ReturnMoment` (`datetime_utc`, `latitude`, `longitude`, `timezone`)
- `NatalBlock` (`planets`, `points`, `angles`, `houses`) — for the `natal` field of the progressions response
- `ProgressedBlock` (`planets`, `points`, `angles`) — no houses

Reuse existing types: `Subject`, `ResolvedSubject`, `Planets`, `Points`, `Angles`, `House`, `Aspect`, `HouseSystem`, `WarningCode`.

## 6. Charts module additions

In `src/astro_api/charts.py`:

- `build_solar_return(subject, location, year, relocation, house_system) -> SolarReturnResponse`
  - Compute exact UTC of the SR for `year` (Immanuel exposes a `SolarReturn` chart class — use it; otherwise compute by binary-searching for `Sun.longitude == natal_sun.longitude` between Jan 1 and Dec 31 of `year`).
  - If `relocation` is `None`: cast at birth location. Else: cast at relocation coords.
  - Same body extraction as `_natal_response`.
- `build_progressions(subject, location, target_date, house_system) -> ProgressionsResponse`
  - Compute `progressed_datetime`: `birth_datetime_utc + (target_date - birth_date)` days. Treat `target_date` as UTC midnight.
  - Build natal chart at birth location.
  - Build progressed chart at `progressed_datetime_utc` and birth location with `aspects_to=natal_chart` so its `aspects` dict carries progressed→natal cross-aspects.
  - Extract `progressed_aspects` via the existing planet→planet helper.

Both raise `DateOutOfRange` on ephemeris bounds. Both pure functions — no env, no I/O beyond Swiss Ephemeris.

## 7. Endpoint wiring

In `src/astro_api/main.py`:

- `@app.post("/v1/solar-return", response_model=SolarReturnResponse, dependencies=[Depends(require_api_key)])`
- `@app.post("/v1/progressions", response_model=ProgressionsResponse, dependencies=[Depends(require_api_key)])`

Each handler:
1. Validate `subject.birth_time is not None` — else raise typed exception → 422 with the per-endpoint error code.
2. `resolve_place(subject.birth_place)` (and `relocation_place` for SR if provided).
3. Surface `multiple_matches` warning per Phase 1 convention.
4. Call the corresponding `build_*` function.
5. Return the response model.

Add the typed exceptions and exception handlers:

- `BirthTimeRequiredForSolarReturn` → 422 `birth_time_required_for_solar_return`
- `BirthTimeRequiredForProgressions` → 422 `birth_time_required_for_progressions`

OpenAPI metadata: clean `operationId`s on both routes (`post_solar_return`, `post_progressions`) so Delegate generates readable tool names.

## 8. Out of scope

- Tertiary / minor progressions
- Solar arc directions (could be Phase 3)
- Lunar returns
- Eclipses
- Fixed stars, asteroids beyond Chiron
- Solar return interpretive narrative (the LLM does that)

## 9. Acceptance criteria

1. `POST /v1/solar-return` for a known subject + year returns a chart envelope with the exact return moment in UTC. Sun longitude in the response matches natal Sun longitude within ±0.001°.
2. SR with `relocation_place` returns a chart cast at the relocated coords; `relocated: true`; `return_moment.latitude`/`longitude`/`timezone` reflect the relocation.
3. SR without `birth_time` returns 422 `birth_time_required_for_solar_return`.
4. `POST /v1/progressions` for a known subject returns natal + progressed positions + `progressed_aspects` sorted by orb.
5. For a subject born N days ≥ 0 ago, with `target_date` = today: `progressed_datetime_utc` ≈ `birth_datetime_utc + N days` (where N = age in years).
6. Progressions without `birth_time` returns 422 `birth_time_required_for_progressions`.
7. Both endpoints appear in `/openapi.json` with `X-API-Key` security required and clean operationIds.
8. After re-running `add_service_from_spec`, Delegate exposes 7 tools (5 from v1 + 2 new), and an end-to-end MCP call to `solar_return` and `progressions` returns structured chart data.

## 10. Open questions

None at spec time. Phase 3 candidates: lunar returns, solar arc directions, eclipses.
