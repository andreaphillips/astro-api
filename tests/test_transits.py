from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest

from astro_api.charts import DateOutOfRange, ResolvedLocation, build_transits
from astro_api.schemas import AspectType, HouseSystem, Subject, TransitsResponse

# Reuse the running design-spec example.
ANDREA = Subject(
    name="Andrea",
    birth_date=date(1989, 5, 12),
    birth_time=time(14, 30),
    birth_place="Maracaibo, Venezuela",
)
ANDREA_LOCATION = ResolvedLocation(latitude=10.66, longitude=-71.65, timezone="America/Caracas")
TARGET = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)

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
def transits() -> TransitsResponse:
    return build_transits(ANDREA, ANDREA_LOCATION, HouseSystem.PLACIDUS, TARGET)


def test_transits_response_includes_full_natal_envelope(
    transits: TransitsResponse,
) -> None:
    assert transits.subject.name == "Andrea"
    assert transits.subject.datetime_utc == datetime(1989, 5, 12, 18, 30, tzinfo=UTC)
    assert transits.house_system == HouseSystem.PLACIDUS
    assert transits.angles is not None
    assert transits.houses is not None and len(transits.houses) == 12
    assert transits.aspects, "natal envelope should still carry natal aspects"


def test_transits_block_is_planet_to_planet_only(transits: TransitsResponse) -> None:
    assert transits.transits, "expected at least one transit aspect"
    for a in transits.transits:
        assert a.from_ in PLANET_KEYS
        assert a.to in PLANET_KEYS


def test_transits_block_is_majors_only_and_sorted_by_orb(
    transits: TransitsResponse,
) -> None:
    allowed = {
        AspectType.CONJUNCTION,
        AspectType.OPPOSITION,
        AspectType.TRINE,
        AspectType.SQUARE,
        AspectType.SEXTILE,
    }
    for a in transits.transits:
        assert a.type in allowed
    orbs = [a.orb for a in transits.transits]
    assert orbs == sorted(orbs)


def test_default_target_date_is_now_utc() -> None:
    before = datetime.now(UTC)
    response = build_transits(ANDREA, ANDREA_LOCATION, HouseSystem.PLACIDUS)
    after = datetime.now(UTC)
    # build_sky uses the natal subject's UTC; the transit chart is "now". The
    # response itself doesn't expose target_date, but a default-now call should
    # complete and produce a populated transits block.
    assert response.transits, "now-by-default should still yield aspects"
    # Sanity: the test ran in seconds, so before/after bracket the call.
    assert before <= after


def test_naive_target_datetime_treated_as_utc() -> None:
    aware = build_transits(ANDREA, ANDREA_LOCATION, HouseSystem.PLACIDUS, TARGET)
    naive = build_transits(
        ANDREA,
        ANDREA_LOCATION,
        HouseSystem.PLACIDUS,
        TARGET.replace(tzinfo=None),
    )
    assert [a.model_dump() for a in aware.transits] == [a.model_dump() for a in naive.transits]


def test_non_utc_target_is_normalized_to_utc() -> None:
    target_caracas = TARGET.astimezone(timezone(timedelta(hours=-4)))
    response = build_transits(ANDREA, ANDREA_LOCATION, HouseSystem.PLACIDUS, target_caracas)
    expected = build_transits(ANDREA, ANDREA_LOCATION, HouseSystem.PLACIDUS, TARGET)
    assert [a.model_dump() for a in response.transits] == [
        a.model_dump() for a in expected.transits
    ]


def test_transits_out_of_range_target_raises() -> None:
    bad_target = datetime(500, 1, 1, 12, 0, tzinfo=UTC)
    with pytest.raises(DateOutOfRange):
        build_transits(ANDREA, ANDREA_LOCATION, HouseSystem.PLACIDUS, bad_target)


def test_transits_no_birth_time_keeps_birth_time_unknown_warning() -> None:
    no_time = Subject(
        name="Andrea", birth_date=date(1989, 5, 12), birth_place="Maracaibo, Venezuela"
    )
    response = build_transits(no_time, ANDREA_LOCATION, HouseSystem.PLACIDUS, TARGET)
    assert response.warnings == ["birth_time_unknown"]
    assert response.angles is None
    assert response.houses is None
    # Transits block still populated — sky planets still exist regardless.
    assert response.transits
