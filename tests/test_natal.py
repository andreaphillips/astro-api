from datetime import UTC, date, datetime, time

import pytest

from astro_api.charts import DateOutOfRange, ResolvedLocation, build_natal
from astro_api.schemas import (
    Angles,
    AspectType,
    Dignity,
    HouseSystem,
    NatalResponse,
    SignName,
    Subject,
)

# Reference subject — Andrea, the running example throughout the design spec.
ANDREA = Subject(
    name="Andrea",
    birth_date=date(1989, 5, 12),
    birth_time=time(14, 30),
    birth_place="Maracaibo, Venezuela",
)
ANDREA_LOCATION = ResolvedLocation(latitude=10.66, longitude=-71.65, timezone="America/Caracas")

EXPECTED_PLANETS = (
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
)
EXPECTED_POINTS = ("north_node", "south_node", "lilith", "vertex", "part_of_fortune")
EXPECTED_ANGLES = ("ascendant", "midheaven", "descendant", "imum_coeli")


@pytest.fixture(scope="module")
def chart() -> NatalResponse:
    """Build the reference chart once — Immanuel does measurable work per call."""
    return build_natal(ANDREA, ANDREA_LOCATION, HouseSystem.PLACIDUS)


# ---------- Happy path: full chart with birth_time ----------


def test_subject_block_resolved_to_utc(chart: NatalResponse) -> None:
    # 14:30 in America/Caracas (UTC-4) → 18:30 UTC.
    assert chart.subject.datetime_utc == datetime(1989, 5, 12, 18, 30, tzinfo=UTC)
    assert chart.subject.timezone == "America/Caracas"
    assert chart.subject.latitude == 10.66
    assert chart.subject.longitude == -71.65
    assert chart.subject.name == "Andrea"


def test_house_system_echoed(chart: NatalResponse) -> None:
    assert chart.house_system == HouseSystem.PLACIDUS


def test_all_planets_present_with_well_formed_placements(chart: NatalResponse) -> None:
    dumped = chart.planets.model_dump()
    assert tuple(dumped.keys()) == EXPECTED_PLANETS
    for name in EXPECTED_PLANETS:
        placement = getattr(chart.planets, name)
        assert isinstance(placement.sign, SignName)
        assert 0.0 <= placement.degree < 30.0
        assert placement.house is not None and 1 <= placement.house <= 12
        assert isinstance(placement.dignity, Dignity)
        assert isinstance(placement.weight, float)


def test_all_points_present_and_part_of_fortune_populated(chart: NatalResponse) -> None:
    dumped = chart.points.model_dump()
    assert tuple(dumped.keys()) == EXPECTED_POINTS
    assert chart.points.part_of_fortune is not None
    assert 0.0 <= chart.points.part_of_fortune.degree < 30.0


def test_angles_populated_when_birth_time_given(chart: NatalResponse) -> None:
    assert chart.angles is not None
    assert isinstance(chart.angles, Angles)
    for name in EXPECTED_ANGLES:
        ang = getattr(chart.angles, name)
        assert isinstance(ang.sign, SignName)
        assert 0.0 <= ang.degree < 30.0


def test_houses_are_twelve_in_order(chart: NatalResponse) -> None:
    assert chart.houses is not None
    assert len(chart.houses) == 12
    assert [h.number for h in chart.houses] == list(range(1, 13))
    for h in chart.houses:
        assert isinstance(h.sign, SignName)
        assert 0.0 <= h.cusp_degree < 30.0


def test_aspects_are_majors_only_and_sorted_by_orb(chart: NatalResponse) -> None:
    assert chart.aspects, "expected at least one aspect for a normal natal chart"
    allowed = {
        AspectType.CONJUNCTION,
        AspectType.OPPOSITION,
        AspectType.TRINE,
        AspectType.SQUARE,
        AspectType.SEXTILE,
    }
    for a in chart.aspects:
        assert a.type in allowed
    orbs = [a.orb for a in chart.aspects]
    assert orbs == sorted(orbs)


def test_aspect_endpoints_reference_known_bodies(chart: NatalResponse) -> None:
    valid = set(EXPECTED_PLANETS) | set(EXPECTED_POINTS) | set(EXPECTED_ANGLES)
    for a in chart.aspects:
        assert a.from_ in valid
        assert a.to in valid


def test_aspects_dedupe_pairs(chart: NatalResponse) -> None:
    """Each unordered (a, b) pair should appear at most once."""
    pairs = [tuple(sorted((a.from_, a.to))) for a in chart.aspects]
    assert len(pairs) == len(set(pairs))


def test_warnings_empty_when_birth_time_provided(chart: NatalResponse) -> None:
    assert chart.warnings == []


# ---------- Edge case: missing birth_time ----------


def test_no_birth_time_nulls_houses_angles_and_part_of_fortune() -> None:
    subject = Subject(
        name="Andrea",
        birth_date=date(1989, 5, 12),
        birth_place="Maracaibo, Venezuela",
    )
    response = build_natal(subject, ANDREA_LOCATION, HouseSystem.PLACIDUS)

    assert response.houses is None
    assert response.angles is None
    assert response.points.part_of_fortune is None
    # Other points still populated — only PoF depends on the angle.
    assert response.points.north_node is not None
    assert response.points.lilith is not None


def test_no_birth_time_appends_birth_time_unknown_warning() -> None:
    subject = Subject(birth_date=date(1989, 5, 12), birth_place="Maracaibo, Venezuela")
    response = build_natal(subject, ANDREA_LOCATION, HouseSystem.PLACIDUS)
    assert response.warnings == ["birth_time_unknown"]


def test_no_birth_time_keeps_planet_signs_but_drops_house() -> None:
    subject = Subject(birth_date=date(1989, 5, 12), birth_place="Maracaibo, Venezuela")
    response = build_natal(subject, ANDREA_LOCATION, HouseSystem.PLACIDUS)
    for name in EXPECTED_PLANETS:
        placement = getattr(response.planets, name)
        assert isinstance(placement.sign, SignName)
        assert placement.house is None


def test_no_birth_time_uses_noon_local_for_utc_subject() -> None:
    subject = Subject(birth_date=date(1989, 5, 12), birth_place="Maracaibo, Venezuela")
    response = build_natal(subject, ANDREA_LOCATION, HouseSystem.PLACIDUS)
    # Noon America/Caracas (UTC-4) → 16:00 UTC.
    assert response.subject.datetime_utc == datetime(1989, 5, 12, 16, 0, tzinfo=UTC)


# ---------- Edge case: alternate house system passes through ----------


def test_whole_sign_house_system_is_honored() -> None:
    response = build_natal(ANDREA, ANDREA_LOCATION, HouseSystem.WHOLE_SIGN)
    assert response.house_system == HouseSystem.WHOLE_SIGN
    assert response.houses is not None
    # In whole-sign houses every cusp falls at 0° of its sign.
    for h in response.houses:
        assert h.cusp_degree == pytest.approx(0.0, abs=1e-9)


# ---------- Edge case: out-of-range birth date ----------


def test_date_outside_ephemeris_range_raises_date_out_of_range() -> None:
    subject = Subject(
        birth_date=date(500, 1, 1),
        birth_time=time(12, 0),
        birth_place="London, UK",
    )
    location = ResolvedLocation(latitude=51.5, longitude=-0.12, timezone="Europe/London")
    with pytest.raises(DateOutOfRange):
        build_natal(subject, location, HouseSystem.PLACIDUS)


# ---------- Pure-function discipline ----------


def test_build_natal_does_not_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Strip everything that would normally configure settings; build_natal must not care.
    monkeypatch.delenv("ASTRO_API_KEY", raising=False)
    monkeypatch.delenv("DEFAULT_HOUSE_SYSTEM", raising=False)
    monkeypatch.delenv("NOMINATIM_USER_AGENT", raising=False)
    response = build_natal(ANDREA, ANDREA_LOCATION, HouseSystem.PLACIDUS)
    assert response.house_system == HouseSystem.PLACIDUS
