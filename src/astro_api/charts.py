from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import swisseph as swe
from immanuel import charts as immanuel_charts
from immanuel.const import calc as immanuel_calc
from immanuel.const import chart as immanuel_chart
from immanuel.setup import settings as immanuel_settings

from astro_api.schemas import (
    Angle,
    Angles,
    Aspect,
    AspectType,
    Dignity,
    House,
    HouseSystem,
    NatalResponse,
    PlanetPlacement,
    Planets,
    PointPlacement,
    Points,
    ResolvedSubject,
    SignName,
    Subject,
)

__all__ = ["DateOutOfRange", "ResolvedLocation", "build_natal"]


@dataclass(frozen=True)
class ResolvedLocation:
    """Geocoded subject location. Produced by the geocoding layer (T3)."""

    latitude: float
    longitude: float
    timezone: str  # IANA timezone name, e.g. "America/Caracas"


class DateOutOfRange(Exception):
    """Raised when the birth date falls outside the available ephemeris range."""


_HOUSE_SYSTEM_CODES: dict[HouseSystem, int] = {
    HouseSystem.PLACIDUS: immanuel_chart.PLACIDUS,
    HouseSystem.WHOLE_SIGN: immanuel_chart.WHOLE_SIGN,
    HouseSystem.KOCH: immanuel_chart.KOCH,
    HouseSystem.EQUAL: immanuel_chart.EQUAL,
}

_PLANET_KEYS: dict[int, str] = {
    immanuel_chart.SUN: "sun",
    immanuel_chart.MOON: "moon",
    immanuel_chart.MERCURY: "mercury",
    immanuel_chart.VENUS: "venus",
    immanuel_chart.MARS: "mars",
    immanuel_chart.JUPITER: "jupiter",
    immanuel_chart.SATURN: "saturn",
    immanuel_chart.URANUS: "uranus",
    immanuel_chart.NEPTUNE: "neptune",
    immanuel_chart.PLUTO: "pluto",
    immanuel_chart.CHIRON: "chiron",
}

_POINT_KEYS: dict[int, str] = {
    immanuel_chart.NORTH_NODE: "north_node",
    immanuel_chart.SOUTH_NODE: "south_node",
    immanuel_chart.LILITH: "lilith",  # Black Moon Lilith (mean) per spec §5.2
    immanuel_chart.VERTEX: "vertex",
    immanuel_chart.PART_OF_FORTUNE: "part_of_fortune",
}

_ANGLE_KEYS: dict[int, str] = {
    immanuel_chart.ASC: "ascendant",
    immanuel_chart.MC: "midheaven",
    immanuel_chart.DESC: "descendant",
    immanuel_chart.IC: "imum_coeli",
}

_BODY_KEYS: dict[int, str] = {**_PLANET_KEYS, **_POINT_KEYS, **_ANGLE_KEYS}

_FIVE_MAJORS: list[float] = [
    immanuel_calc.CONJUNCTION,
    immanuel_calc.OPPOSITION,
    immanuel_calc.SQUARE,
    immanuel_calc.TRINE,
    immanuel_calc.SEXTILE,
]

_ASPECT_TYPE_BY_NAME: dict[str, AspectType] = {
    "Conjunction": AspectType.CONJUNCTION,
    "Opposition": AspectType.OPPOSITION,
    "Trine": AspectType.TRINE,
    "Square": AspectType.SQUARE,
    "Sextile": AspectType.SEXTILE,
}


def _configure_immanuel(house_system: HouseSystem) -> None:
    """Configure the Immanuel singleton for our supported scope.

    Idempotent — safe to call before every chart build.
    """
    immanuel_settings.house_system = _HOUSE_SYSTEM_CODES[house_system]
    immanuel_settings.aspects = list(_FIVE_MAJORS)
    immanuel_settings.objects = [
        immanuel_chart.ASC,
        immanuel_chart.DESC,
        immanuel_chart.MC,
        immanuel_chart.IC,
        immanuel_chart.NORTH_NODE,
        immanuel_chart.SOUTH_NODE,
        immanuel_chart.VERTEX,
        immanuel_chart.PART_OF_FORTUNE,
        immanuel_chart.LILITH,
        immanuel_chart.SUN,
        immanuel_chart.MOON,
        immanuel_chart.MERCURY,
        immanuel_chart.VENUS,
        immanuel_chart.MARS,
        immanuel_chart.JUPITER,
        immanuel_chart.SATURN,
        immanuel_chart.URANUS,
        immanuel_chart.NEPTUNE,
        immanuel_chart.PLUTO,
        immanuel_chart.CHIRON,
    ]


def _dignity(state: Any) -> Dignity:
    if state.ruler:
        return Dignity.DOMICILE
    if state.exalted:
        return Dignity.EXALTATION
    if state.detriment:
        return Dignity.DETRIMENT
    if state.fall:
        return Dignity.FALL
    if state.peregrine:
        return Dignity.PEREGRINE
    return Dignity.NEUTRAL


def _sign(name: str) -> SignName:
    return SignName(name.lower())


def _planet_placement(obj: Any, *, include_house: bool) -> PlanetPlacement:
    # Asteroids (Chiron) lack dignities/score in Immanuel — default to neutral/0.
    dignities_state = getattr(obj, "dignities", None)
    score = getattr(obj, "score", 0)
    return PlanetPlacement(
        sign=_sign(obj.sign.name),
        degree=float(obj.sign_longitude.raw),
        house=obj.house.number if include_house else None,
        retrograde=bool(obj.movement.retrograde),
        dignity=_dignity(dignities_state) if dignities_state is not None else Dignity.NEUTRAL,
        weight=float(score),
    )


def _point_placement(obj: Any, *, include_house: bool) -> PointPlacement:
    return PointPlacement(
        sign=_sign(obj.sign.name),
        degree=float(obj.sign_longitude.raw),
        house=obj.house.number if include_house else None,
    )


def _angle(obj: Any) -> Angle:
    return Angle(sign=_sign(obj.sign.name), degree=float(obj.sign_longitude.raw))


def _extract_aspects(natal: Any) -> list[Aspect]:
    """Collect 5-major aspects, dedup A↔B pairs, sort by orb ascending."""
    seen: set[tuple[int, int]] = set()
    out: list[Aspect] = []
    for pairs in natal.aspects.values():
        for asp in pairs.values():
            a, b = asp.active, asp.passive
            if a not in _BODY_KEYS or b not in _BODY_KEYS:
                continue
            if asp.type not in _ASPECT_TYPE_BY_NAME:
                continue
            pair = (a, b) if a <= b else (b, a)
            if pair in seen:
                continue
            seen.add(pair)
            out.append(
                Aspect.model_validate(
                    {
                        "from": _BODY_KEYS[a],
                        "to": _BODY_KEYS[b],
                        "type": _ASPECT_TYPE_BY_NAME[asp.type].value,
                        "orb": float(asp.orb),
                        "applying": bool(asp.movement.applicative),
                    }
                )
            )
    out.sort(key=lambda a: a.orb)
    return out


def _local_naive_string(birth_date: Any, birth_time: time | None) -> str:
    t = birth_time if birth_time is not None else time(12, 0)
    return datetime.combine(birth_date, t).strftime("%Y-%m-%d %H:%M:%S")


def _utc_datetime(birth_date: Any, birth_time: time | None, tz_name: str) -> datetime:
    t = birth_time if birth_time is not None else time(12, 0)
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as e:
        raise ValueError(f"Unknown timezone: {tz_name!r}") from e
    return datetime.combine(birth_date, t, tzinfo=tz).astimezone(ZoneInfo("UTC"))


def build_natal(
    subject: Subject,
    location: ResolvedLocation,
    house_system: HouseSystem,
) -> NatalResponse:
    """Compute a natal chart for the given subject and location.

    Pure function: no env access, no I/O beyond the in-process Swiss Ephemeris.
    Caller is responsible for geocoding `subject.birth_place` into `location` and
    for surfacing geocoding warnings (e.g. ``multiple_matches``).
    """
    _configure_immanuel(house_system)
    birth_time_unknown = subject.birth_time is None

    immanuel_subject = immanuel_charts.Subject(
        date_time=_local_naive_string(subject.birth_date, subject.birth_time),
        latitude=location.latitude,
        longitude=location.longitude,
        timezone=location.timezone,
    )

    try:
        natal = immanuel_charts.Natal(immanuel_subject)
        # Touch every object so an out-of-range error surfaces here, not later.
        for idx in (*_PLANET_KEYS, *_POINT_KEYS, *_ANGLE_KEYS):
            _ = natal.objects[idx].sign.name
    except swe.Error as e:
        raise DateOutOfRange(str(e)) from e

    planets = Planets(
        **{
            key: _planet_placement(natal.objects[idx], include_house=not birth_time_unknown)
            for idx, key in _PLANET_KEYS.items()
        }
    )

    points_kwargs: dict[str, PointPlacement | None] = {}
    for idx, key in _POINT_KEYS.items():
        if key == "part_of_fortune" and birth_time_unknown:
            points_kwargs[key] = None
        else:
            points_kwargs[key] = _point_placement(
                natal.objects[idx], include_house=not birth_time_unknown
            )
    points = Points(**points_kwargs)

    if birth_time_unknown:
        angles: Angles | None = None
        houses: list[House] | None = None
    else:
        angles = Angles(**{key: _angle(natal.objects[idx]) for idx, key in _ANGLE_KEYS.items()})
        houses = sorted(
            (
                House(
                    number=h.number,
                    sign=_sign(h.sign.name),
                    cusp_degree=float(h.sign_longitude.raw),
                )
                for h in natal.houses.values()
            ),
            key=lambda h: h.number,
        )

    aspects = _extract_aspects(natal)

    warnings: list[str] = []
    if birth_time_unknown:
        warnings.append("birth_time_unknown")

    return NatalResponse(
        subject=ResolvedSubject(
            name=subject.name,
            datetime_utc=_utc_datetime(subject.birth_date, subject.birth_time, location.timezone),
            latitude=location.latitude,
            longitude=location.longitude,
            timezone=location.timezone,
        ),
        house_system=house_system,
        planets=planets,
        points=points,
        angles=angles,
        houses=houses,
        aspects=aspects,
        warnings=warnings,
    )
