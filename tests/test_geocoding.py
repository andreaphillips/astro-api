from unittest.mock import MagicMock

import pytest
from geopy.exc import GeocoderTimedOut

from astro_api import geocoding
from astro_api.geocoding import (
    GeocodingTimeout,
    PlaceNotFound,
    ResolvedLocation,
    resolve_place,
)


class _FakeLocation:
    def __init__(self, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude


@pytest.fixture(autouse=True)
def _clear_geocoding_cache() -> None:
    resolve_place.cache_clear()
    yield
    resolve_place.cache_clear()


def _patch_nominatim(monkeypatch: pytest.MonkeyPatch, geocode_mock: MagicMock) -> None:
    instance = MagicMock()
    instance.geocode = geocode_mock
    monkeypatch.setattr(geocoding, "Nominatim", lambda **_: instance)


def test_resolve_place_success(monkeypatch: pytest.MonkeyPatch) -> None:
    geocode = MagicMock(return_value=[_FakeLocation(40.7128, -74.0060)])
    _patch_nominatim(monkeypatch, geocode)

    result = resolve_place("New York, NY")

    assert isinstance(result, ResolvedLocation)
    assert result.latitude == pytest.approx(40.7128)
    assert result.longitude == pytest.approx(-74.0060)
    assert result.timezone == "America/New_York"
    assert result.warnings == ()
    geocode.assert_called_once()


def test_resolve_place_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    geocode = MagicMock(return_value=[])
    _patch_nominatim(monkeypatch, geocode)

    with pytest.raises(PlaceNotFound):
        resolve_place("Nowhereville, ZZ")


def test_resolve_place_multiple_matches_returns_first_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    geocode = MagicMock(
        return_value=[
            _FakeLocation(43.6532, -79.3832),
            _FakeLocation(35.6892, 139.6917),
        ]
    )
    _patch_nominatim(monkeypatch, geocode)

    result = resolve_place("Springfield")

    assert result.latitude == pytest.approx(43.6532)
    assert result.longitude == pytest.approx(-79.3832)
    assert result.warnings == ("multiple_matches",)


def test_resolve_place_timeout_raises_geocoding_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    geocode = MagicMock(side_effect=GeocoderTimedOut("nominatim took too long"))
    _patch_nominatim(monkeypatch, geocode)

    with pytest.raises(GeocodingTimeout):
        resolve_place("Anywhere")
    assert geocode.call_count == 1


def test_resolve_place_lru_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    geocode = MagicMock(return_value=[_FakeLocation(40.7128, -74.0060)])
    _patch_nominatim(monkeypatch, geocode)

    first = resolve_place("New York, NY")
    second = resolve_place("New York, NY")

    assert first == second
    assert geocode.call_count == 1
