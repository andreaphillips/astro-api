from datetime import UTC, date, datetime, time

import pytest

from astro_api.charts import ResolvedLocation, build_synastry
from astro_api.schemas import AspectType, HouseSystem, Subject, SynastryResponse

ANDREA = Subject(
    name="Andrea",
    birth_date=date(1989, 5, 12),
    birth_time=time(14, 30),
    birth_place="Maracaibo, Venezuela",
)
ANDREA_LOCATION = ResolvedLocation(latitude=10.66, longitude=-71.65, timezone="America/Caracas")
SISTER = Subject(
    name="Sister",
    birth_date=date(1992, 8, 15),
    birth_time=time(9, 0),
    birth_place="Maracaibo, Venezuela",
)
SISTER_LOCATION = ANDREA_LOCATION  # same city for the test fixture

VALID_BODIES = {
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
    "north_node",
    "south_node",
    "lilith",
    "vertex",
    "part_of_fortune",
    "ascendant",
    "midheaven",
    "descendant",
    "imum_coeli",
}


@pytest.fixture(scope="module")
def synastry() -> SynastryResponse:
    return build_synastry(ANDREA, ANDREA_LOCATION, SISTER, SISTER_LOCATION, HouseSystem.PLACIDUS)


def test_synastry_returns_both_charts_in_full(synastry: SynastryResponse) -> None:
    assert synastry.subject_a.subject.name == "Andrea"
    assert synastry.subject_a.subject.datetime_utc == datetime(1989, 5, 12, 18, 30, tzinfo=UTC)
    assert synastry.subject_a.angles is not None
    assert synastry.subject_a.houses is not None and len(synastry.subject_a.houses) == 12
    assert synastry.subject_a.aspects, "subject_a should carry its own natal aspects"

    assert synastry.subject_b.subject.name == "Sister"
    assert synastry.subject_b.angles is not None
    assert synastry.subject_b.houses is not None and len(synastry.subject_b.houses) == 12
    assert synastry.subject_b.aspects, "subject_b should carry its own natal aspects"


def test_cross_aspects_use_a_to_b_orientation(synastry: SynastryResponse) -> None:
    assert synastry.synastry.cross_aspects, "expected at least one cross-aspect"
    for ca in synastry.synastry.cross_aspects:
        assert ca.from_a in VALID_BODIES
        assert ca.to_b in VALID_BODIES


def test_cross_aspects_are_majors_only_and_sorted(synastry: SynastryResponse) -> None:
    allowed = {
        AspectType.CONJUNCTION,
        AspectType.OPPOSITION,
        AspectType.TRINE,
        AspectType.SQUARE,
        AspectType.SEXTILE,
    }
    for ca in synastry.synastry.cross_aspects:
        assert ca.type in allowed
    orbs = [ca.orb for ca in synastry.synastry.cross_aspects]
    assert orbs == sorted(orbs)


def test_synastry_response_has_no_highlights(synastry: SynastryResponse) -> None:
    """Spec §5.4: cross_aspects only — no `highlights` field."""
    dumped = synastry.model_dump()
    assert set(dumped["synastry"].keys()) == {"cross_aspects"}


def test_synastry_warnings_default_to_empty(synastry: SynastryResponse) -> None:
    assert synastry.warnings == []


def test_synastry_propagates_per_subject_birth_time_unknown_warning() -> None:
    no_time = Subject(
        name="Mystery", birth_date=date(1989, 5, 12), birth_place="Maracaibo, Venezuela"
    )
    response = build_synastry(
        no_time, ANDREA_LOCATION, SISTER, SISTER_LOCATION, HouseSystem.PLACIDUS
    )
    assert "birth_time_unknown" in response.subject_a.warnings
    assert response.subject_a.angles is None
    assert response.subject_b.warnings == []
    # Cross aspects still populated even when one chart has no birth time —
    # planets are still placed at noon.
    assert response.synastry.cross_aspects


def test_swap_subjects_swaps_cross_aspect_direction() -> None:
    forward = build_synastry(ANDREA, ANDREA_LOCATION, SISTER, SISTER_LOCATION, HouseSystem.PLACIDUS)
    reverse = build_synastry(SISTER, SISTER_LOCATION, ANDREA, ANDREA_LOCATION, HouseSystem.PLACIDUS)
    # Same number of cross-aspects (the relation is symmetric in pair count).
    assert len(forward.synastry.cross_aspects) == len(reverse.synastry.cross_aspects)
    # And each forward (a→b) entry's orb appears as a reverse (b→a) entry of
    # the same orb — verifying we labeled directions consistently.
    forward_keys = sorted(
        (ca.from_a, ca.to_b, ca.type, round(ca.orb, 6)) for ca in forward.synastry.cross_aspects
    )
    reverse_keys = sorted(
        (ca.to_b, ca.from_a, ca.type, round(ca.orb, 6)) for ca in reverse.synastry.cross_aspects
    )
    assert forward_keys == reverse_keys
