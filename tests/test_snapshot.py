"""Snapshot test against a known reference natal chart (spec §11.10).

Acceptance criterion §11.10: a known reference chart matches astro.com within
±0.05° on all major planets.

------------------------------------------------------------------------------
Reference subject
------------------------------------------------------------------------------
Diana, Princess of Wales — birth data is Astrodatabank Rodden-rated **AA**
(the highest reliability category, "as recorded on birth certificate"):
    https://www.astro.com/astro-databank/Diana,_Princess_of_Wales

  birth_date : 1961-07-01
  birth_time : 19:45 BST  → 18:45 UTC
  birth_place: Sandringham, England (52.83°N, 0.50°E, Europe/London)
  house_sys  : Placidus

Both astro.com and our API run the same Swiss Ephemeris kernel under the hood
(astro.com uses Swiss Ephemeris directly; we use Immanuel, which wraps it), so
the two produce identical longitudes within Swiss Ephemeris precision (<0.001°).

------------------------------------------------------------------------------
Regenerating the snapshot
------------------------------------------------------------------------------
If an Immanuel or Swiss Ephemeris update shifts these values beyond ±0.05°,
the procedure to refresh ``tests/fixtures/known_charts.json`` is:

  1. Run the same Subject through ``charts.build_natal`` (NOT astro.com — see
     note below) to capture the new engine output:

         uv run python -c "
         import os; os.environ['ASTRO_API_KEY']='regen'
         from datetime import date, time
         from astro_api.charts import ResolvedLocation, build_natal
         from astro_api.schemas import HouseSystem, Subject
         subject  = Subject(name='Diana, Princess of Wales',
                            birth_date=date(1961, 7, 1),
                            birth_time=time(19, 45),
                            birth_place='Sandringham, England')
         location = ResolvedLocation(52.8333, 0.5, 'Europe/London')
         resp     = build_natal(subject, location, HouseSystem.PLACIDUS)
         for k, v in resp.planets.model_dump().items():
             print(k, v['sign'], round(v['degree'], 2))"

  2. Cross-check against astro.com (same date/time/place, Placidus). If the
     two diverge by more than ~0.05° **the engine is broken** — do not blindly
     overwrite the snapshot; investigate the divergence first.
  3. Update the ``expected_planets`` block in ``known_charts.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from astro_api import geocoding
from astro_api import main as main_module
from astro_api.geocoding import ResolvedLocation
from astro_api.main import app
from astro_api.settings import get_settings

API_KEY = "test-snapshot"
TOLERANCE_DEGREES = 0.05
FIXTURES_PATH = Path(__file__).parent / "fixtures" / "known_charts.json"


@pytest.fixture
def known_charts() -> dict[str, Any]:
    return json.loads(FIXTURES_PATH.read_text())


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ASTRO_API_KEY", API_KEY)
    get_settings.cache_clear()
    geocoding.resolve_place.cache_clear()
    return TestClient(app)


def test_diana_natal_chart_matches_snapshot_within_tolerance(
    client: TestClient,
    known_charts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = known_charts["diana_princess_of_wales"]
    subject = fixture["subject"]
    loc = fixture["resolved_location"]
    expected = fixture["expected_planets"]

    pre_resolved = ResolvedLocation(
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        timezone=loc["timezone"],
    )
    monkeypatch.setattr(main_module, "resolve_place", lambda _place: pre_resolved)

    response = client.post(
        "/v1/natal",
        json={"subject": subject, "house_system": fixture["house_system"]},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200, response.text

    actual_planets = response.json()["planets"]

    mismatched: list[str] = []
    for name, ref in expected.items():
        actual = actual_planets[name]
        if actual["sign"] != ref["sign"]:
            mismatched.append(f"{name}: sign {actual['sign']!r} != expected {ref['sign']!r}")
            continue
        delta = abs(actual["degree"] - ref["degree"])
        if delta > TOLERANCE_DEGREES:
            mismatched.append(
                f"{name}: degree {actual['degree']:.4f} differs from "
                f"{ref['degree']:.2f} by {delta:.4f}° (> {TOLERANCE_DEGREES}°)"
            )

    assert not mismatched, "Snapshot drift:\n  " + "\n  ".join(mismatched)
