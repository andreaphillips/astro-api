from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from geopy.exc import GeocoderTimedOut
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

from astro_api.settings import get_settings

__all__ = [
    "GeocodingTimeout",
    "MultipleMatches",
    "PlaceNotFound",
    "ResolvedLocation",
    "WarningCode",
    "resolve_place",
]


WarningCode = Literal["multiple_matches"]


class PlaceNotFound(Exception):
    """Nominatim returned no matches for the given place string."""


class MultipleMatches(Exception):
    """Nominatim returned multiple matches for the given place string.

    The function still returns the first result; the warning code
    `multiple_matches` is surfaced via ``ResolvedLocation.warnings`` for
    upstream callers to include in their response payload.
    """


class GeocodingTimeout(Exception):
    """Nominatim request timed out. No retry is attempted."""


@dataclass(frozen=True)
class ResolvedLocation:
    latitude: float
    longitude: float
    timezone: str
    warnings: tuple[WarningCode, ...] = ()


_tz_finder = TimezoneFinder()


def _normalize(place: str) -> str:
    return " ".join(place.strip().lower().split())


def _build_geocoder() -> Nominatim:
    settings = get_settings()
    return Nominatim(
        user_agent=settings.nominatim_user_agent,
        timeout=settings.nominatim_timeout_seconds,
    )


@lru_cache(maxsize=512)
def _resolve_normalized(normalized: str) -> ResolvedLocation:
    geocoder = _build_geocoder()
    try:
        results = geocoder.geocode(normalized, exactly_one=False, limit=2)
    except GeocoderTimedOut as exc:
        raise GeocodingTimeout(str(exc)) from exc

    if not results:
        raise PlaceNotFound(normalized)

    first = results[0]
    timezone = _tz_finder.timezone_at(lat=first.latitude, lng=first.longitude)
    if timezone is None:
        raise PlaceNotFound(normalized)

    warnings: tuple[WarningCode, ...] = ("multiple_matches",) if len(results) > 1 else ()
    return ResolvedLocation(
        latitude=float(first.latitude),
        longitude=float(first.longitude),
        timezone=timezone,
        warnings=warnings,
    )


def resolve_place(place: str) -> ResolvedLocation:
    """Resolve a free-text place string to (latitude, longitude, IANA timezone).

    Cached in-process via ``functools.lru_cache(maxsize=512)`` keyed by the
    normalized (case- and whitespace-folded) place string.
    """
    return _resolve_normalized(_normalize(place))


resolve_place.cache_clear = _resolve_normalized.cache_clear  # type: ignore[attr-defined]
resolve_place.cache_info = _resolve_normalized.cache_info  # type: ignore[attr-defined]
