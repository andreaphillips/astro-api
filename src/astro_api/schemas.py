from datetime import date, datetime, time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from astro_api.settings import HouseSystem

__all__ = [
    "Angle",
    "Angles",
    "Aspect",
    "AspectType",
    "CrossAspect",
    "Dignity",
    "ErrorResponse",
    "House",
    "HouseSystem",
    "NatalRequest",
    "NatalResponse",
    "Planets",
    "PlanetPlacement",
    "Points",
    "PointPlacement",
    "ResolvedSubject",
    "SignName",
    "SkyResponse",
    "Subject",
    "Synastry",
    "SynastryRequest",
    "SynastryResponse",
    "TransitsRequest",
    "TransitsResponse",
    "WarningCode",
]


class SignName(StrEnum):
    ARIES = "aries"
    TAURUS = "taurus"
    GEMINI = "gemini"
    CANCER = "cancer"
    LEO = "leo"
    VIRGO = "virgo"
    LIBRA = "libra"
    SCORPIO = "scorpio"
    SAGITTARIUS = "sagittarius"
    CAPRICORN = "capricorn"
    AQUARIUS = "aquarius"
    PISCES = "pisces"


class AspectType(StrEnum):
    CONJUNCTION = "conjunction"
    OPPOSITION = "opposition"
    TRINE = "trine"
    SQUARE = "square"
    SEXTILE = "sextile"


class Dignity(StrEnum):
    DOMICILE = "domicile"
    EXALTATION = "exaltation"
    DETRIMENT = "detriment"
    FALL = "fall"
    PEREGRINE = "peregrine"
    NEUTRAL = "neutral"


WarningCode = Literal["multiple_matches", "birth_time_unknown"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Subject(_StrictModel):
    name: str | None = None
    birth_date: date
    birth_time: time | None = Field(
        default=None,
        description=(
            "24-hour HH:MM local time. Omit if unknown — chart is computed at noon "
            "local time and warning code 'birth_time_unknown' is returned."
        ),
    )
    birth_place: str = Field(..., min_length=1)


class ResolvedSubject(_StrictModel):
    name: str | None = None
    datetime_utc: datetime
    latitude: float
    longitude: float
    timezone: str


class PlanetPlacement(_StrictModel):
    sign: SignName
    degree: float
    house: int | None
    retrograde: bool
    dignity: Dignity
    weight: float


class PointPlacement(_StrictModel):
    sign: SignName
    degree: float
    house: int | None = None


class Angle(_StrictModel):
    sign: SignName
    degree: float


class House(_StrictModel):
    number: int = Field(..., ge=1, le=12)
    sign: SignName
    cusp_degree: float


class Planets(_StrictModel):
    sun: PlanetPlacement
    moon: PlanetPlacement
    mercury: PlanetPlacement
    venus: PlanetPlacement
    mars: PlanetPlacement
    jupiter: PlanetPlacement
    saturn: PlanetPlacement
    uranus: PlanetPlacement
    neptune: PlanetPlacement
    pluto: PlanetPlacement
    chiron: PlanetPlacement


class Points(_StrictModel):
    north_node: PointPlacement
    south_node: PointPlacement
    lilith: PointPlacement
    vertex: PointPlacement
    part_of_fortune: PointPlacement | None


class Angles(_StrictModel):
    ascendant: Angle
    midheaven: Angle
    descendant: Angle
    imum_coeli: Angle


class Aspect(BaseModel):
    """An aspect between two bodies. JSON key `from` is aliased to `from_` in Python."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(..., alias="from")
    to: str
    type: AspectType
    orb: float
    applying: bool


class CrossAspect(_StrictModel):
    from_a: str
    to_b: str
    type: AspectType
    orb: float
    applying: bool


class Synastry(_StrictModel):
    cross_aspects: list[CrossAspect]


class NatalRequest(_StrictModel):
    subject: Subject
    house_system: HouseSystem | None = None


class NatalResponse(_StrictModel):
    subject: ResolvedSubject
    house_system: HouseSystem
    planets: Planets
    points: Points
    angles: Angles | None
    houses: list[House] | None
    aspects: list[Aspect]
    warnings: list[str] = Field(default_factory=list)


class TransitsRequest(_StrictModel):
    natal_subject: Subject
    target_date: datetime | None = None
    house_system: HouseSystem | None = None


class TransitsResponse(_StrictModel):
    subject: ResolvedSubject
    house_system: HouseSystem
    planets: Planets
    points: Points
    angles: Angles | None
    houses: list[House] | None
    aspects: list[Aspect]
    transits: list[Aspect]
    warnings: list[str] = Field(default_factory=list)


class SynastryRequest(_StrictModel):
    subject_a: Subject
    subject_b: Subject
    house_system: HouseSystem | None = None


class SynastryResponse(_StrictModel):
    subject_a: NatalResponse
    subject_b: NatalResponse
    synastry: Synastry
    warnings: list[str] = Field(default_factory=list)


class SkyResponse(_StrictModel):
    datetime_utc: datetime
    planets: Planets
    points: Points
    angles: Angles | None = None
    warnings: list[str] = Field(default_factory=list)


class ErrorResponse(_StrictModel):
    error: str
    detail: str
