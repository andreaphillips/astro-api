from dataclasses import dataclass
from datetime import UTC, datetime, time
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
    CrossAspect,
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
    SkyResponse,
    Subject,
    Synastry,
    SynastryResponse,
    TransitsResponse,
)

__all__ = [
    "DateOutOfRange",
    "ResolvedLocation",
    "build_natal",
    "build_sky",
    "build_synastry",
    "build_transits",
]


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
    # True nodes (vs mean) so the retrograde flag carries real information —
    # mean nodes are mathematically always retrograde, true nodes can briefly
    # turn direct.
    immanuel_chart.TRUE_NORTH_NODE: "north_node",
    immanuel_chart.TRUE_SOUTH_NODE: "south_node",
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
    # Reassert the Swiss Ephemeris file path on every build. immanuel.__init__
    # sets it once at import time, but under uvicorn the swisseph C-library
    # path can be lost between import and the first request, leading to
    # "SwissEph file 'seas_18.se1' not found" on Chiron. Reasserting here is
    # idempotent and cheap.
    immanuel_settings.set_swe_filepath()
    immanuel_settings.house_system = _HOUSE_SYSTEM_CODES[house_system]
    immanuel_settings.aspects = list(_FIVE_MAJORS)
    immanuel_settings.objects = [
        immanuel_chart.ASC,
        immanuel_chart.DESC,
        immanuel_chart.MC,
        immanuel_chart.IC,
        immanuel_chart.TRUE_NORTH_NODE,
        immanuel_chart.TRUE_SOUTH_NODE,
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
    # Vertex and Part of Fortune are calculated points, not bodies in motion —
    # `movement` is absent or non-meaningful for them. Surface retrograde only
    # when Immanuel reports it (true nodes, Lilith).
    movement = getattr(obj, "movement", None)
    retrograde: bool | None = None
    if movement is not None:
        rx_attr = getattr(movement, "retrograde", None)
        if rx_attr is not None:
            retrograde = bool(rx_attr)
    return PointPlacement(
        sign=_sign(obj.sign.name),
        degree=float(obj.sign_longitude.raw),
        house=obj.house.number if include_house else None,
        retrograde=retrograde,
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


def _extract_planet_to_planet_aspects(chart_with_aspects_to: Any) -> list[Aspect]:
    """Extract cross-chart planet→planet aspects (5 majors only).

    Used for the transits block: the chart was built with ``aspects_to=natal``,
    so each entry's active is in this chart, passive is in the natal chart.
    Spec §5.3: "aspects from the current sky's planets to the natal planets".
    """
    out: list[Aspect] = []
    for active_idx, pairs in chart_with_aspects_to.aspects.items():
        if active_idx not in _PLANET_KEYS:
            continue
        for passive_idx, asp in pairs.items():
            if passive_idx not in _PLANET_KEYS:
                continue
            if asp.type not in _ASPECT_TYPE_BY_NAME:
                continue
            out.append(
                Aspect.model_validate(
                    {
                        "from": _PLANET_KEYS[active_idx],
                        "to": _PLANET_KEYS[passive_idx],
                        "type": _ASPECT_TYPE_BY_NAME[asp.type].value,
                        "orb": float(asp.orb),
                        "applying": bool(asp.movement.applicative),
                    }
                )
            )
    out.sort(key=lambda a: a.orb)
    return out


def _extract_cross_aspects(chart_with_aspects_to: Any) -> list[CrossAspect]:
    """Extract A→B cross-aspects from a chart built with ``aspects_to=other``.

    Active body is in chart A (this chart), passive body is in chart B.
    Used for synastry. 5 majors only, sorted by orb ascending.
    """
    out: list[CrossAspect] = []
    for active_idx, pairs in chart_with_aspects_to.aspects.items():
        if active_idx not in _BODY_KEYS:
            continue
        for passive_idx, asp in pairs.items():
            if passive_idx not in _BODY_KEYS:
                continue
            if asp.type not in _ASPECT_TYPE_BY_NAME:
                continue
            out.append(
                CrossAspect(
                    from_a=_BODY_KEYS[active_idx],
                    to_b=_BODY_KEYS[passive_idx],
                    type=_ASPECT_TYPE_BY_NAME[asp.type],
                    orb=float(asp.orb),
                    applying=bool(asp.movement.applicative),
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


def _build_immanuel_natal(
    subject: Subject,
    location: ResolvedLocation,
    *,
    aspects_to: Any | None = None,
) -> Any:
    """Build an Immanuel Natal chart for ``subject`` at ``location``.

    Settings (house system, aspects, objects) must already be configured by the caller.
    Out-of-range birth dates are translated to ``DateOutOfRange``.
    """
    immanuel_subject = immanuel_charts.Subject(
        date_time=_local_naive_string(subject.birth_date, subject.birth_time),
        latitude=location.latitude,
        longitude=location.longitude,
        timezone=location.timezone,
    )
    try:
        chart = immanuel_charts.Natal(immanuel_subject, aspects_to=aspects_to)
        # Touch every object so out-of-range errors surface here, not later.
        for idx in (*_PLANET_KEYS, *_POINT_KEYS, *_ANGLE_KEYS):
            _ = chart.objects[idx].sign.name
    except swe.Error as e:
        raise DateOutOfRange(str(e)) from e
    return chart


def _natal_response(
    chart: Any,
    *,
    subject: Subject,
    location: ResolvedLocation,
    house_system: HouseSystem,
) -> NatalResponse:
    """Project an Immanuel chart + inputs into our NatalResponse Pydantic model.

    The chart's ``aspects`` (if any) are used as natal-to-natal aspects.
    """
    birth_time_unknown = subject.birth_time is None

    planets = Planets(
        **{
            key: _planet_placement(chart.objects[idx], include_house=not birth_time_unknown)
            for idx, key in _PLANET_KEYS.items()
        }
    )

    points_kwargs: dict[str, PointPlacement | None] = {}
    for idx, key in _POINT_KEYS.items():
        if key == "part_of_fortune" and birth_time_unknown:
            points_kwargs[key] = None
        else:
            points_kwargs[key] = _point_placement(
                chart.objects[idx], include_house=not birth_time_unknown
            )
    points = Points(**points_kwargs)

    if birth_time_unknown:
        angles: Angles | None = None
        houses: list[House] | None = None
    else:
        angles = Angles(**{key: _angle(chart.objects[idx]) for idx, key in _ANGLE_KEYS.items()})
        houses = sorted(
            (
                House(
                    number=h.number,
                    sign=_sign(h.sign.name),
                    cusp_degree=float(h.sign_longitude.raw),
                )
                for h in chart.houses.values()
            ),
            key=lambda h: h.number,
        )

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
        aspects=_extract_aspects(chart),
        warnings=warnings,
    )


def _coerce_utc(dt: datetime | None) -> datetime:
    """Default to ``now`` and force UTC; naive input is treated as already-UTC."""
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def build_natal(
    subject: Subject,
    location: ResolvedLocation,
    house_system: HouseSystem,
) -> NatalResponse:
    """Compute a natal chart for the given subject and location.

    Pure function: no env access, no I/O beyond the in-process Swiss Ephemeris.
    Caller is responsible for geocoding ``subject.birth_place`` into ``location``
    and for surfacing geocoding warnings (e.g. ``multiple_matches``).
    """
    _configure_immanuel(house_system)
    chart = _build_immanuel_natal(subject, location)
    return _natal_response(chart, subject=subject, location=location, house_system=house_system)


def build_transits(
    natal_subject: Subject,
    location: ResolvedLocation,
    house_system: HouseSystem,
    target_date: datetime | None = None,
) -> TransitsResponse:
    """Compute transits to a natal chart at ``target_date`` (UTC; default = now).

    Returns the natal envelope plus a ``transits`` block — aspects from the
    target-sky planets to the natal planets, sorted by orb ascending.
    """
    _configure_immanuel(house_system)
    target_utc = _coerce_utc(target_date)

    natal_chart = _build_immanuel_natal(natal_subject, location)
    natal_envelope = _natal_response(
        natal_chart, subject=natal_subject, location=location, house_system=house_system
    )

    # Build the transit chart at target_utc with the natal location, hooked up to
    # the natal chart so its `aspects` dict contains transit→natal cross-aspects.
    transit_immanuel = immanuel_charts.Subject(
        date_time=target_utc.strftime("%Y-%m-%d %H:%M:%S"),
        latitude=location.latitude,
        longitude=location.longitude,
        timezone="UTC",
    )
    try:
        transit_chart = immanuel_charts.Natal(transit_immanuel, aspects_to=natal_chart)
        for idx in _PLANET_KEYS:
            _ = transit_chart.objects[idx].sign.name
    except swe.Error as e:
        raise DateOutOfRange(str(e)) from e

    transits = _extract_planet_to_planet_aspects(transit_chart)

    return TransitsResponse(
        subject=natal_envelope.subject,
        house_system=natal_envelope.house_system,
        planets=natal_envelope.planets,
        points=natal_envelope.points,
        angles=natal_envelope.angles,
        houses=natal_envelope.houses,
        aspects=natal_envelope.aspects,
        transits=transits,
        warnings=natal_envelope.warnings,
    )


def build_synastry(
    subject_a: Subject,
    location_a: ResolvedLocation,
    subject_b: Subject,
    location_b: ResolvedLocation,
    house_system: HouseSystem,
) -> SynastryResponse:
    """Compare two natal charts. Returns each chart in full plus A→B cross-aspects.

    Per spec §5.4: ``cross_aspects`` only — no ``highlights`` field. The LLM
    client formats human-readable summaries; the API returns structured data.
    """
    _configure_immanuel(house_system)

    chart_a = _build_immanuel_natal(subject_a, location_a)
    chart_b = _build_immanuel_natal(subject_b, location_b)
    response_a = _natal_response(
        chart_a, subject=subject_a, location=location_a, house_system=house_system
    )
    response_b = _natal_response(
        chart_b, subject=subject_b, location=location_b, house_system=house_system
    )

    # Re-build chart A with aspects_to=chart_b so its `aspects` dict holds A→B
    # cross-aspects (active in A, passive in B). The earlier chart_a is reused
    # for response_a; this one is purely for cross-aspect extraction.
    cross_chart = _build_immanuel_natal(subject_a, location_a, aspects_to=chart_b)
    cross_aspects = _extract_cross_aspects(cross_chart)

    return SynastryResponse(
        subject_a=response_a,
        subject_b=response_b,
        synastry=Synastry(cross_aspects=cross_aspects),
        warnings=[],
    )


def build_sky(date_time: datetime | None = None) -> SkyResponse:
    """Current planetary positions at ``date_time`` (UTC; default = now).

    No location → no houses, no angles, no part-of-fortune. Vertex is also
    location-dependent and is omitted by setting it from a Greenwich default
    that the LLM client should treat as approximate (planets/points are
    location-independent and authoritative).
    """
    # House system doesn't matter for sky (we don't expose houses), but Immanuel
    # still needs one set; default to placidus.
    _configure_immanuel(HouseSystem.PLACIDUS)
    dt_utc = _coerce_utc(date_time)

    sky_subject = immanuel_charts.Subject(
        date_time=dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
        latitude=0.0,
        longitude=0.0,
        timezone="UTC",
    )
    try:
        chart = immanuel_charts.Natal(sky_subject)
        for idx in (*_PLANET_KEYS, *_POINT_KEYS):
            _ = chart.objects[idx].sign.name
    except swe.Error as e:
        raise DateOutOfRange(str(e)) from e

    planets = Planets(
        **{
            key: _planet_placement(chart.objects[idx], include_house=False)
            for idx, key in _PLANET_KEYS.items()
        }
    )
    points = Points(
        **{
            key: _point_placement(chart.objects[idx], include_house=False)
            for idx, key in _POINT_KEYS.items()
        }
    )

    return SkyResponse(
        datetime_utc=dt_utc,
        planets=planets,
        points=points,
        angles=None,
        warnings=[],
    )
