from datetime import UTC, date, datetime, time, timedelta

import pytest
from immanuel.const import calc

from astro_api.charts import (
    DateOutOfRange,
    ResolvedLocation,
    build_progressions,
)
from astro_api.schemas import AspectType, HouseSystem, ProgressionsResponse, Subject

# Reuse the spec's running example. Andrea, born in Costa Rica.
ANDREA = Subject(
    name="Andrea",
    birth_date=date(1980, 12, 9),
    birth_time=time(10, 35),
    birth_place="San José, Costa Rica",
)
BIRTH_LOCATION = ResolvedLocation(latitude=9.93, longitude=-84.08, timezone="America/Costa_Rica")
TARGET = date(2026, 4, 27)

PLANET_KEYS = {
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
    "chiron",
}


@pytest.fixture(scope="module")
def progressions() -> ProgressionsResponse:
    return build_progressions(ANDREA, BIRTH_LOCATION, TARGET, HouseSystem.PLACIDUS)


# ---------- §9.5 / §4: day-for-a-year progressed datetime ----------


def test_progressed_datetime_is_birth_plus_n_days_for_n_year_old() -> None:
    # A subject who is exactly N years old (elapsed = N tropical years) must have
    # a progressed moment exactly N ephemeris days after birth (day-for-a-year).
    n_years = 44
    target = date(2026, 4, 27)
    target_utc = datetime.combine(target, time(0, 0), tzinfo=UTC)
    birth_utc = target_utc - timedelta(days=n_years * calc.YEAR_DAYS)
    # Build the subject from that exact birth instant, at a UTC location so the
    # resolved birth datetime equals birth_utc to the second.
    subject = Subject(
        birth_date=birth_utc.date(),
        birth_time=birth_utc.time().replace(microsecond=0),
        birth_place="Null Island",
    )
    utc_location = ResolvedLocation(latitude=0.0, longitude=0.0, timezone="UTC")

    response = build_progressions(subject, utc_location, target, HouseSystem.PLACIDUS)

    expected = response.subject.datetime_utc + timedelta(days=n_years)
    delta = abs((response.progressed_datetime_utc - expected).total_seconds())
    assert delta <= 1.0


def test_target_date_defaults_to_today_utc() -> None:
    response = build_progressions(ANDREA, BIRTH_LOCATION, None, HouseSystem.PLACIDUS)
    assert response.target_date == datetime.now(UTC).date()


def test_target_date_echoed_in_response(progressions: ProgressionsResponse) -> None:
    assert progressions.target_date == TARGET


# ---------- §4: natal has houses, progressed does not ----------


def test_natal_block_has_full_envelope(progressions: ProgressionsResponse) -> None:
    assert progressions.natal.angles is not None
    assert progressions.natal.houses is not None
    assert len(progressions.natal.houses) == 12
    assert progressions.natal.points.part_of_fortune is not None


def test_progressed_block_has_no_houses(progressions: ProgressionsResponse) -> None:
    # ProgressedBlock has no houses field at all (the natal houses are the frame).
    assert "houses" not in type(progressions.progressed).model_fields
    assert progressions.progressed.angles is not None


def test_progression_advances_positions(progressions: ProgressionsResponse) -> None:
    # Day-for-a-year moves bodies: the progressed Sun differs from the natal Sun.
    natal_sun = progressions.natal.planets.sun
    prog_sun = progressions.progressed.planets.sun
    assert (natal_sun.sign, natal_sun.degree) != (prog_sun.sign, prog_sun.degree)


# ---------- §4: progressed_aspects ----------


def test_progressed_aspects_are_planet_to_planet_majors_sorted(
    progressions: ProgressionsResponse,
) -> None:
    allowed = {
        AspectType.CONJUNCTION,
        AspectType.OPPOSITION,
        AspectType.TRINE,
        AspectType.SQUARE,
        AspectType.SEXTILE,
    }
    aspects = progressions.progressed_aspects
    assert aspects, "expected at least one progressed→natal aspect"
    orbs = [a.orb for a in aspects]
    assert orbs == sorted(orbs)
    for a in aspects:
        assert a.type in allowed
        # `from` = progressed body, `to` = natal body — both planets.
        assert a.from_ in PLANET_KEYS
        assert a.to in PLANET_KEYS


# ---------- Out of range ----------


def test_out_of_range_birth_raises() -> None:
    subject = Subject(
        birth_date=date(500, 1, 1),
        birth_time=time(12, 0),
        birth_place="London, UK",
    )
    location = ResolvedLocation(latitude=51.5, longitude=-0.12, timezone="Europe/London")
    with pytest.raises(DateOutOfRange):
        build_progressions(subject, location, date(545, 1, 1), HouseSystem.PLACIDUS)
