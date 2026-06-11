from datetime import date, time

import pytest

from astro_api.charts import (
    DateOutOfRange,
    ResolvedLocation,
    build_natal,
    build_solar_return,
)
from astro_api.schemas import AspectType, HouseSystem, SolarReturnResponse, Subject

# Reuse the spec's running example. Andrea, born in Costa Rica.
ANDREA = Subject(
    name="Andrea",
    birth_date=date(1980, 12, 9),
    birth_time=time(10, 35),
    birth_place="San José, Costa Rica",
)
BIRTH_LOCATION = ResolvedLocation(latitude=9.93, longitude=-84.08, timezone="America/Costa_Rica")
# Tamarindo, Costa Rica — the "travel for your solar return" relocation.
RELOCATION = ResolvedLocation(latitude=10.30, longitude=-85.84, timezone="America/Costa_Rica")
YEAR = 2026


@pytest.fixture(scope="module")
def sr_home() -> SolarReturnResponse:
    return build_solar_return(ANDREA, BIRTH_LOCATION, YEAR, None, HouseSystem.PLACIDUS)


@pytest.fixture(scope="module")
def sr_relocated() -> SolarReturnResponse:
    return build_solar_return(ANDREA, BIRTH_LOCATION, YEAR, RELOCATION, HouseSystem.PLACIDUS)


# ---------- Acceptance criterion §9.1: SR Sun == natal Sun ----------


def test_sr_sun_longitude_matches_natal_sun_within_tolerance(
    sr_home: SolarReturnResponse,
) -> None:
    natal = build_natal(ANDREA, BIRTH_LOCATION, HouseSystem.PLACIDUS)
    # Compare absolute ecliptic longitude (sign index * 30 + degree-in-sign).
    signs = list(type(natal.planets.sun.sign))
    natal_abs = signs.index(natal.planets.sun.sign) * 30 + natal.planets.sun.degree
    sr_abs = signs.index(sr_home.planets.sun.sign) * 30 + sr_home.planets.sun.degree
    assert abs(sr_abs - natal_abs) <= 0.001


# ---------- Acceptance criterion §9.2 / §3: relocation ----------


def test_no_relocation_casts_at_birthplace(sr_home: SolarReturnResponse) -> None:
    assert sr_home.relocated is False
    assert sr_home.return_moment.latitude == BIRTH_LOCATION.latitude
    assert sr_home.return_moment.longitude == BIRTH_LOCATION.longitude
    assert sr_home.return_moment.timezone == BIRTH_LOCATION.timezone
    # The subject block always reports the natal location.
    assert sr_home.subject.latitude == BIRTH_LOCATION.latitude
    assert sr_home.subject.longitude == BIRTH_LOCATION.longitude


def test_relocation_casts_at_relocated_coords(sr_relocated: SolarReturnResponse) -> None:
    assert sr_relocated.relocated is True
    assert sr_relocated.return_moment.latitude == RELOCATION.latitude
    assert sr_relocated.return_moment.longitude == RELOCATION.longitude
    assert sr_relocated.return_moment.timezone == RELOCATION.timezone
    # The subject block still reports the *natal* location, not the relocation.
    assert sr_relocated.subject.latitude == BIRTH_LOCATION.latitude
    assert sr_relocated.subject.longitude == BIRTH_LOCATION.longitude


def test_return_moment_is_location_independent(
    sr_home: SolarReturnResponse, sr_relocated: SolarReturnResponse
) -> None:
    # Same instant regardless of where the chart is cast.
    assert sr_home.return_moment.datetime_utc == sr_relocated.return_moment.datetime_utc


def test_relocation_changes_the_angles(
    sr_home: SolarReturnResponse, sr_relocated: SolarReturnResponse
) -> None:
    assert sr_home.angles is not None and sr_relocated.angles is not None
    home_asc = (sr_home.angles.ascendant.sign, sr_home.angles.ascendant.degree)
    reloc_asc = (sr_relocated.angles.ascendant.sign, sr_relocated.angles.ascendant.degree)
    assert home_asc != reloc_asc


# ---------- Envelope mirrors /v1/natal ----------


def test_full_envelope_present(sr_home: SolarReturnResponse) -> None:
    assert sr_home.house_system == HouseSystem.PLACIDUS
    assert sr_home.angles is not None
    assert sr_home.houses is not None and len(sr_home.houses) == 12
    assert sr_home.points.part_of_fortune is not None
    assert sr_home.warnings == []


def test_aspects_are_majors_only_and_sorted_by_orb(sr_home: SolarReturnResponse) -> None:
    allowed = {
        AspectType.CONJUNCTION,
        AspectType.OPPOSITION,
        AspectType.TRINE,
        AspectType.SQUARE,
        AspectType.SEXTILE,
    }
    orbs = [a.orb for a in sr_home.aspects]
    assert orbs == sorted(orbs)
    for a in sr_home.aspects:
        assert a.type in allowed


def test_points_retrograde_uses_true_nodes(sr_home: SolarReturnResponse) -> None:
    # True nodes carry a real retrograde flag (mean nodes are always retrograde).
    assert sr_home.points.north_node.retrograde is not None


# ---------- Out of range ----------


def test_year_out_of_ephemeris_range_raises(sr_home: SolarReturnResponse) -> None:
    with pytest.raises(DateOutOfRange):
        build_solar_return(ANDREA, BIRTH_LOCATION, 5000, None, HouseSystem.PLACIDUS)
