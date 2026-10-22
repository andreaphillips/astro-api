from datetime import date, time

import pytest

from astro_api.charts import ResolvedLocation, build_composite, build_natal
from astro_api.schemas import CompositeResponse, HouseSystem, Subject

ANDREA = Subject(
    name="Andrea",
    birth_date=date(1989, 5, 12),
    birth_time=time(14, 30),
    birth_place="Maracaibo, Venezuela",
)
SISTER = Subject(
    name="Sister",
    birth_date=date(1992, 8, 15),
    birth_time=time(9, 0),
    birth_place="Caracas, Venezuela",
)
MARACAIBO = ResolvedLocation(latitude=10.66, longitude=-71.65, timezone="America/Caracas")
CARACAS = ResolvedLocation(latitude=10.5, longitude=-66.9, timezone="America/Caracas")

SIGNS = [
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]  # fmt: skip


def _lon(p) -> float:
    return SIGNS.index(p.sign.value) * 30 + p.degree


def _short_arc_midpoint(a: float, b: float) -> float:
    mid = (a + b) / 2
    return (mid + 180) % 360 if abs(a - b) > 180 else mid


@pytest.fixture(scope="module")
def composite() -> CompositeResponse:
    return build_composite(ANDREA, MARACAIBO, SISTER, CARACAS, HouseSystem.PLACIDUS)


def test_planets_sit_at_short_arc_midpoint_of_both_natals(composite: CompositeResponse) -> None:
    a = build_natal(ANDREA, MARACAIBO, HouseSystem.PLACIDUS)
    b = build_natal(SISTER, CARACAS, HouseSystem.PLACIDUS)
    for key in ("sun", "moon", "venus", "mars", "saturn"):
        expected = _short_arc_midpoint(_lon(getattr(a.planets, key)), _lon(getattr(b.planets, key)))
        assert _lon(getattr(composite.planets, key)) == pytest.approx(expected, abs=0.01), key


def test_full_chart_when_both_times_known(composite: CompositeResponse) -> None:
    assert composite.subject_a.name == "Andrea"
    assert composite.subject_b.name == "Sister"
    assert composite.angles is not None
    assert composite.houses is not None and len(composite.houses) == 12
    assert composite.points.vertex is not None
    assert composite.aspects
    assert composite.warnings == []


def test_either_time_unknown_drops_time_dependent_parts() -> None:
    sister_no_time = SISTER.model_copy(update={"birth_time": None})
    result = build_composite(ANDREA, MARACAIBO, sister_no_time, CARACAS, HouseSystem.PLACIDUS)
    assert result.angles is None
    assert result.houses is None
    assert result.points.vertex is None
    assert result.points.part_of_fortune is None
    assert result.planets.sun.house is None
    assert result.warnings == ["birth_time_unknown"]
    # Andrea's own resolved time is untouched by the other subject's fallback.
    assert result.subject_a.datetime_utc.hour == 18


def test_whole_sign_houses_start_at_composite_ascendant_sign() -> None:
    # Sister at 18:00 puts the midpoint Asc at 29° Scorpio while Immanuel's
    # midpoint-ARMC houses would start house 1 in Sagittarius.
    sister_evening = SISTER.model_copy(update={"birth_time": time(18, 0)})
    result = build_composite(ANDREA, MARACAIBO, sister_evening, CARACAS, HouseSystem.WHOLE_SIGN)
    assert result.angles is not None and result.houses is not None
    asc_sign = result.angles.ascendant.sign
    assert asc_sign.value == "scorpio"
    assert result.houses[0].sign == asc_sign
    asc = SIGNS.index(asc_sign.value)
    assert [h.sign.value for h in result.houses] == [SIGNS[(asc + n) % 12] for n in range(12)]
    for key, placement in [*result.planets, *result.points]:
        expected = (SIGNS.index(placement.sign.value) - asc) % 12 + 1
        assert placement.house == expected, key
