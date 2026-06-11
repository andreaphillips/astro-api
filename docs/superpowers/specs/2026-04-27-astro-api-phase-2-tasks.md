# Astro API — Phase 2 Task Breakdown (TaskHive-ready)

**Date:** 2026-04-27
**Author:** Aura (PM agent)
**Status:** Ready to load into TaskHive
**Source spec:** [Phase 2 spec](./2026-04-27-astro-api-phase-2.md) — authoritative; this file is just the decomposition.

Mirrors the Phase 1 pipeline shape (schemas → charts builders → endpoint wiring → ingest).
Load the epic first, then the five tasks with the dependencies below. Each runs through the
standard PM → Dev → QA pipeline.

## Dependency graph

```
P2-1 (schemas)
  ├─► P2-2 (build_solar_return) ─┐
  └─► P2-3 (build_progressions) ─┴─► P2-4 (endpoints + exceptions) ─► P2-5 (Delegate re-ingest + e2e)
```

P2-2 and P2-3 are independent once P2-1 lands → assign to two Dev agents in parallel.

---

## Epic — Phase 2: Solar Return + Progressions

**Priority:** high
**Goal:** Add `POST /v1/solar-return` and `POST /v1/progressions`, then re-ingest so Delegate
exposes **7 tools (5 → 7)**. Same stack, conventions, auth, deploy as Phase 1.
**Spec:** full Phase 2 spec doc. **Out of scope:** spec §8 (tertiary/minor progressions,
solar arc, lunar returns, eclipses, fixed stars, narrative).

---

## P2-1 — Schemas: solar-return + progressions models

**Priority:** high · **Depends on:** none · **Spec:** §5

Add to `src/astro_api/schemas.py`:

- `SolarReturnRequest` — `subject: Subject`, `year: int`, `relocation_place: str | None = None`, `house_system: HouseSystem | None = None`
- `SolarReturnResponse` — `subject: ResolvedSubject`, `return_moment: ReturnMoment`, `relocated: bool`, `house_system`, `planets`, `points`, `angles`, `houses`, `aspects`, `warnings`
- `ProgressionsRequest` — `subject: Subject`, `target_date: date | None = None`, `house_system: HouseSystem | None = None`
- `ProgressionsResponse` — `subject: ResolvedSubject`, `target_date`, `progressed_datetime_utc`, `house_system`, `natal: NatalBlock`, `progressed: ProgressedBlock`, `progressed_aspects: list[Aspect]`, `warnings`
- `ReturnMoment` — `datetime_utc`, `latitude`, `longitude`, `timezone`
- `NatalBlock` — `planets`, `points`, `angles`, `houses`
- `ProgressedBlock` — `planets`, `points`, `angles` (**no `houses`**)

Reuse existing types: `Subject`, `ResolvedSubject`, `Planets`, `Points`, `Angles`, `House`, `Aspect`, `HouseSystem`, `WarningCode`.

**Tests** (`tests/test_schemas.py`): models import + round-trip serialize; required-field validation
(`subject`/`year` required); `relocation_place`/`target_date` optional with correct defaults;
`ProgressedBlock` has no `houses` field.

**Acceptance:** all seven models defined and validated; reuse (no duplicate point/aspect types).

---

## P2-2 — charts.build_solar_return

**Priority:** high · **Depends on:** P2-1 · **Spec:** §3, §6

Implement `build_solar_return(subject, location, year, relocation, house_system) -> SolarReturnResponse`
in `src/astro_api/charts.py`:

- Compute exact UTC of the SR for `year` — use Immanuel's `SolarReturn` chart class if available;
  otherwise binary-search for `Sun.longitude == natal_sun.longitude` between Jan 1 and Dec 31 of `year`.
- `relocation is None` → cast at birth location; else cast at relocation coords. Set `relocated`
  and `return_moment` (datetime_utc + lat/lon/tz of the cast location) accordingly.
- Same body extraction as natal: planets, points (with retrograde), angles, 12 houses,
  5-major aspects sorted by orb ascending.
- Raise `DateOutOfRange` on ephemeris bounds. Pure function — no env, no I/O beyond Swiss Ephemeris.

**Tests:** SR Sun longitude matches natal Sun within ±0.001° (spec criterion 1); relocation path
sets `relocated: true` + relocated coords in `return_moment` (criterion 2); out-of-range year → `DateOutOfRange`.

---

## P2-3 — charts.build_progressions

**Priority:** high · **Depends on:** P2-1 · **Spec:** §4, §6

Implement `build_progressions(subject, location, target_date, house_system) -> ProgressionsResponse`
in `src/astro_api/charts.py`:

- `progressed_datetime = birth_datetime_utc + (target_date - birth_date)` days; treat `target_date`
  as UTC midnight; default = today UTC.
- Build natal chart at birth location.
- Build progressed chart at `progressed_datetime_utc` and birth location with `aspects_to=natal_chart`;
  extract `progressed_aspects` (progressed→natal, 5 majors only, sorted by orb asc; `from` = progressed body, `to` = natal body).
- `progressed` block has **no houses** (natal houses are the reference frame).
- Raise `DateOutOfRange` on bounds. Pure function.

**Tests:** for a subject born N years ago with `target_date` = today, `progressed_datetime_utc ≈
birth_datetime_utc + N days` (criterion 5); `progressed_aspects` sorted by orb; no `houses` in progressed block.

---

## P2-4 — Endpoint wiring + typed exceptions

**Priority:** high · **Depends on:** P2-2, P2-3 · **Spec:** §7

In `src/astro_api/main.py`:

- `@app.post("/v1/solar-return", response_model=SolarReturnResponse, dependencies=[Depends(require_api_key)])` — operationId `post_solar_return`
- `@app.post("/v1/progressions", response_model=ProgressionsResponse, dependencies=[Depends(require_api_key)])` — operationId `post_progressions`

Each handler: validate `subject.birth_time is not None` (else typed 422); `resolve_place(birth_place)`
(+ `relocation_place` for SR if provided); surface `multiple_matches` warning per Phase 1 convention;
call the matching `build_*`; return the response model.

Add typed exceptions + handlers:
- `BirthTimeRequiredForSolarReturn` → 422 `birth_time_required_for_solar_return`
- `BirthTimeRequiredForProgressions` → 422 `birth_time_required_for_progressions`

**Tests** (`tests/test_solar_return.py`, `tests/test_progressions.py`): happy path both endpoints;
422 + correct code when `birth_time` missing (criteria 3, 6); auth required (401 without key);
both appear in `/openapi.json` with `X-API-Key` security + clean operationIds (criterion 7).

**Acceptance:** spec §9 criteria 1–7.

---

## P2-5 — Delegate re-ingest + end-to-end (5 → 7 tools)

**Priority:** high · **Depends on:** P2-4 · **Spec:** §2, §9 criterion 8

After merge → Railway auto-deploys. Then:
- Re-run `mcp__claude_ai_Delegate-Smart__add_service_from_spec` with the deployed `/openapi.json`
  URL and the `X-API-Key` header.
- Verify Delegate exposes **7 tools** (5 from v1 + `solar_return` + `progressions`).
- E2e: invoke the `solar_return` and `progressions` MCP tools, confirm structured chart data returns.

**Note:** requires deploy to Railway (auto on merge to `main`) **and** the Delegate MCP connected
in the session running this task.

**Acceptance:** spec §9 criterion 8.
