from datetime import UTC, datetime, timedelta, timezone

import pytest

from astro_api.charts import DateOutOfRange, build_sky
from astro_api.schemas import SignName, SkyResponse


@pytest.fixture(scope="module")
def sky() -> SkyResponse:
    return build_sky(datetime(2026, 4, 26, 12, 0, tzinfo=UTC))


def test_datetime_utc_echoed(sky: SkyResponse) -> None:
    assert sky.datetime_utc == datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def test_all_planets_present_without_houses(sky: SkyResponse) -> None:
    expected = (
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
    dumped = sky.planets.model_dump()
    assert tuple(dumped.keys()) == expected
    for name in expected:
        placement = getattr(sky.planets, name)
        assert isinstance(placement.sign, SignName)
        assert 0.0 <= placement.degree < 30.0
        assert placement.house is None  # spec §5.5: no houses (no location)


def test_points_have_no_houses(sky: SkyResponse) -> None:
    expected = ("north_node", "south_node", "lilith", "vertex", "part_of_fortune")
    dumped = sky.points.model_dump()
    assert tuple(dumped.keys()) == expected
    for name in expected:
        placement = getattr(sky.points, name)
        assert placement is not None
        assert placement.house is None


def test_angles_are_none_for_sky(sky: SkyResponse) -> None:
    assert sky.angles is None


def test_warnings_default_to_empty(sky: SkyResponse) -> None:
    assert sky.warnings == []


def test_default_date_time_is_now_utc() -> None:
    before = datetime.now(UTC)
    sky = build_sky()
    after = datetime.now(UTC)
    assert before.replace(microsecond=0) <= sky.datetime_utc.replace(microsecond=0)
    assert sky.datetime_utc.replace(microsecond=0) <= after.replace(microsecond=0)


def test_naive_datetime_treated_as_utc() -> None:
    aware = build_sky(datetime(2026, 4, 26, 12, 0, tzinfo=UTC))
    naive = build_sky(datetime(2026, 4, 26, 12, 0))
    assert aware.planets.sun.degree == pytest.approx(naive.planets.sun.degree)
    assert naive.datetime_utc.tzinfo == UTC


def test_non_utc_input_normalized_to_utc() -> None:
    target = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)
    same_in_caracas = target.astimezone(timezone(timedelta(hours=-4)))
    expected = build_sky(target)
    actual = build_sky(same_in_caracas)
    assert actual.datetime_utc == expected.datetime_utc
    assert actual.planets.sun.degree == pytest.approx(expected.planets.sun.degree)


def test_sky_out_of_range_raises() -> None:
    with pytest.raises(DateOutOfRange):
        build_sky(datetime(500, 1, 1, 12, 0, tzinfo=UTC))
