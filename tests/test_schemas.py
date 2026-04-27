from datetime import UTC, date, datetime, time

import pytest
from pydantic import ValidationError

from astro_api.schemas import (
    Angle,
    Angles,
    Aspect,
    AspectType,
    CrossAspect,
    Dignity,
    ErrorResponse,
    House,
    HouseSystem,
    NatalRequest,
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
    SynastryRequest,
    SynastryResponse,
    TransitsRequest,
    TransitsResponse,
    WarningCode,
)


def _make_planet(
    sign: SignName = SignName.TAURUS,
    degree: float = 21.83,
    house: int | None = 7,
    retrograde: bool = False,
    dignity: Dignity = Dignity.NEUTRAL,
    weight: float = 4.2,
) -> PlanetPlacement:
    return PlanetPlacement(
        sign=sign,
        degree=degree,
        house=house,
        retrograde=retrograde,
        dignity=dignity,
        weight=weight,
    )


def _make_planets(house: int | None = 7) -> Planets:
    return Planets(
        sun=_make_planet(SignName.TAURUS, 21.83, house),
        moon=_make_planet(SignName.LEO, 4.21, house),
        mercury=_make_planet(SignName.GEMINI, 1.0, house),
        venus=_make_planet(SignName.CANCER, 1.0, house),
        mars=_make_planet(SignName.LIBRA, 1.0, house),
        jupiter=_make_planet(SignName.VIRGO, 1.0, house),
        saturn=_make_planet(SignName.SCORPIO, 1.0, house),
        uranus=_make_planet(SignName.SAGITTARIUS, 1.0, house),
        neptune=_make_planet(SignName.CAPRICORN, 1.0, house),
        pluto=_make_planet(SignName.PISCES, 1.0, house),
        chiron=_make_planet(SignName.ARIES, 1.0, house),
    )


_UNSET = object()


def _make_points(part_of_fortune: PointPlacement | None | object = _UNSET) -> Points:
    p = PointPlacement(sign=SignName.SCORPIO, degree=10.0, house=1)
    fortune = (
        PointPlacement(sign=SignName.LEO, degree=5.0, house=10)
        if part_of_fortune is _UNSET
        else part_of_fortune
    )
    return Points(
        north_node=p,
        south_node=p,
        lilith=p,
        vertex=p,
        part_of_fortune=fortune,  # type: ignore[arg-type]
    )


def _make_angles() -> Angles:
    return Angles(
        ascendant=Angle(sign=SignName.SCORPIO, degree=12.4),
        midheaven=Angle(sign=SignName.LEO, degree=23.1),
        descendant=Angle(sign=SignName.TAURUS, degree=12.4),
        imum_coeli=Angle(sign=SignName.AQUARIUS, degree=23.1),
    )


def _make_houses() -> list[House]:
    return [House(number=i, sign=SignName.SCORPIO, cusp_degree=12.4 + i) for i in range(1, 13)]


def _make_resolved_subject() -> ResolvedSubject:
    return ResolvedSubject(
        name="Andrea",
        datetime_utc=datetime(1989, 5, 12, 18, 30, tzinfo=UTC),
        latitude=10.66,
        longitude=-71.65,
        timezone="America/Caracas",
    )


# ---------- Enums ----------


def test_sign_name_values_match_spec() -> None:
    assert {s.value for s in SignName} == {
        "aries",
        "taurus",
        "gemini",
        "cancer",
        "leo",
        "virgo",
        "libra",
        "scorpio",
        "sagittarius",
        "capricorn",
        "aquarius",
        "pisces",
    }


def test_aspect_type_is_majors_only() -> None:
    assert {a.value for a in AspectType} == {
        "conjunction",
        "opposition",
        "trine",
        "square",
        "sextile",
    }


def test_dignity_values_match_spec() -> None:
    assert {d.value for d in Dignity} == {
        "domicile",
        "exaltation",
        "detriment",
        "fall",
        "peregrine",
        "neutral",
    }


def test_house_system_re_exported_from_settings() -> None:
    # schemas.HouseSystem must be the same enum used by settings,
    # so request models accept exactly the configured values.
    from astro_api.settings import HouseSystem as SettingsHouseSystem

    assert HouseSystem is SettingsHouseSystem
    assert {h.value for h in HouseSystem} == {"placidus", "whole_sign", "koch", "equal"}


def test_warning_code_literal() -> None:
    # Literal types are runtime-introspectable via typing
    from typing import get_args

    assert set(get_args(WarningCode)) == {"multiple_matches", "birth_time_unknown"}


# ---------- Subject ----------


def test_subject_minimal_valid_payload() -> None:
    subject = Subject(birth_date=date(1989, 5, 12), birth_place="Maracaibo, Venezuela")
    assert subject.name is None
    assert subject.birth_time is None


def test_subject_full_payload_matches_spec_example() -> None:
    subject = Subject.model_validate(
        {
            "name": "Andrea",
            "birth_date": "1989-05-12",
            "birth_time": "14:30",
            "birth_place": "Maracaibo, Venezuela",
        }
    )
    assert subject.name == "Andrea"
    assert subject.birth_date == date(1989, 5, 12)
    assert subject.birth_time == time(14, 30)
    assert subject.birth_place == "Maracaibo, Venezuela"


def test_subject_birth_date_required() -> None:
    with pytest.raises(ValidationError):
        Subject.model_validate({"birth_place": "Maracaibo, Venezuela"})


def test_subject_birth_place_required_and_non_empty() -> None:
    with pytest.raises(ValidationError):
        Subject.model_validate({"birth_date": "1989-05-12"})
    with pytest.raises(ValidationError):
        Subject.model_validate({"birth_date": "1989-05-12", "birth_place": ""})


def test_subject_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Subject.model_validate(
            {
                "birth_date": "1989-05-12",
                "birth_place": "Maracaibo, Venezuela",
                "rising_sign": "scorpio",
            }
        )


# ---------- NatalRequest ----------


def test_natal_request_default_house_system_is_none() -> None:
    request = NatalRequest.model_validate(
        {
            "subject": {
                "birth_date": "1989-05-12",
                "birth_place": "Maracaibo, Venezuela",
            }
        }
    )
    assert request.house_system is None


def test_natal_request_accepts_each_allowed_house_system() -> None:
    for hs in ("placidus", "whole_sign", "koch", "equal"):
        request = NatalRequest.model_validate(
            {
                "subject": {
                    "birth_date": "1989-05-12",
                    "birth_place": "Maracaibo, Venezuela",
                },
                "house_system": hs,
            }
        )
        assert request.house_system == HouseSystem(hs)


def test_natal_request_rejects_unknown_house_system() -> None:
    with pytest.raises(ValidationError):
        NatalRequest.model_validate(
            {
                "subject": {
                    "birth_date": "1989-05-12",
                    "birth_place": "Maracaibo, Venezuela",
                },
                "house_system": "topocentric",
            }
        )


# ---------- Aspect / CrossAspect ----------


def test_aspect_uses_from_alias_in_json() -> None:
    aspect = Aspect.model_validate(
        {"from": "sun", "to": "moon", "type": "trine", "orb": 1.4, "applying": True}
    )
    assert aspect.from_ == "sun"
    assert aspect.to == "moon"

    dumped = aspect.model_dump(by_alias=True)
    assert "from" in dumped
    assert "from_" not in dumped
    assert dumped["from"] == "sun"


def test_aspect_can_also_be_populated_by_python_name() -> None:
    aspect = Aspect.model_validate(
        {"from_": "sun", "to": "moon", "type": "sextile", "orb": 0.5, "applying": False}
    )
    assert aspect.from_ == "sun"


def test_cross_aspect_uses_from_a_to_b_keys() -> None:
    cross = CrossAspect.model_validate(
        {
            "from_a": "sun",
            "to_b": "moon",
            "type": "trine",
            "orb": 2.1,
            "applying": True,
        }
    )
    assert cross.from_a == "sun"
    assert cross.to_b == "moon"
    dumped = cross.model_dump()
    assert dumped == {
        "from_a": "sun",
        "to_b": "moon",
        "type": "trine",
        "orb": 2.1,
        "applying": True,
    }


# ---------- NatalResponse ----------


def test_natal_response_round_trip_with_full_chart() -> None:
    response = NatalResponse(
        subject=_make_resolved_subject(),
        house_system=HouseSystem.PLACIDUS,
        planets=_make_planets(),
        points=_make_points(),
        angles=_make_angles(),
        houses=_make_houses(),
        aspects=[
            Aspect.model_validate(
                {
                    "from": "sun",
                    "to": "moon",
                    "type": "trine",
                    "orb": 1.4,
                    "applying": True,
                }
            )
        ],
    )

    dumped = response.model_dump(by_alias=True, mode="json")
    # Top-level structure matches spec §5.2 exactly.
    assert set(dumped.keys()) == {
        "subject",
        "house_system",
        "planets",
        "points",
        "angles",
        "houses",
        "aspects",
        "warnings",
    }
    assert dumped["aspects"][0]["from"] == "sun"
    assert dumped["warnings"] == []
    assert len(dumped["houses"]) == 12


def test_natal_response_warnings_default_to_empty_list() -> None:
    response = NatalResponse(
        subject=_make_resolved_subject(),
        house_system=HouseSystem.PLACIDUS,
        planets=_make_planets(),
        points=_make_points(),
        angles=_make_angles(),
        houses=_make_houses(),
        aspects=[],
    )
    assert response.warnings == []


def test_natal_response_birth_time_unknown_allows_null_houses_angles_fortune() -> None:
    # Per spec §5.1: when birth_time omitted, houses, angles, and points.part_of_fortune
    # are returned as null.
    response = NatalResponse(
        subject=_make_resolved_subject(),
        house_system=HouseSystem.PLACIDUS,
        planets=_make_planets(house=None),
        points=_make_points(part_of_fortune=None),
        angles=None,
        houses=None,
        aspects=[],
        warnings=["birth_time_unknown"],
    )
    dumped = response.model_dump(by_alias=True, mode="json")
    assert dumped["angles"] is None
    assert dumped["houses"] is None
    assert dumped["points"]["part_of_fortune"] is None
    assert dumped["points"]["north_node"] is not None
    assert dumped["warnings"] == ["birth_time_unknown"]


# ---------- TransitsRequest / Response ----------


def test_transits_request_target_date_optional() -> None:
    request = TransitsRequest.model_validate(
        {
            "natal_subject": {
                "birth_date": "1989-05-12",
                "birth_place": "Maracaibo, Venezuela",
            }
        }
    )
    assert request.target_date is None


def test_transits_request_parses_iso_target_date() -> None:
    request = TransitsRequest.model_validate(
        {
            "natal_subject": {
                "birth_date": "1989-05-12",
                "birth_place": "Maracaibo, Venezuela",
            },
            "target_date": "2026-04-26T12:00:00Z",
        }
    )
    assert request.target_date == datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def test_transits_response_includes_transits_block() -> None:
    response = TransitsResponse(
        subject=_make_resolved_subject(),
        house_system=HouseSystem.PLACIDUS,
        planets=_make_planets(),
        points=_make_points(),
        angles=_make_angles(),
        houses=_make_houses(),
        aspects=[],
        transits=[
            Aspect.model_validate(
                {
                    "from": "saturn",
                    "to": "sun",
                    "type": "square",
                    "orb": 0.3,
                    "applying": True,
                }
            )
        ],
    )
    dumped = response.model_dump(by_alias=True, mode="json")
    assert "transits" in dumped
    assert dumped["transits"][0]["from"] == "saturn"


# ---------- SynastryRequest / Response ----------


def test_synastry_request_requires_both_subjects() -> None:
    with pytest.raises(ValidationError):
        SynastryRequest.model_validate(
            {
                "subject_a": {
                    "birth_date": "1989-05-12",
                    "birth_place": "Maracaibo, Venezuela",
                }
            }
        )


def test_synastry_response_has_only_cross_aspects_no_highlights() -> None:
    chart = NatalResponse(
        subject=_make_resolved_subject(),
        house_system=HouseSystem.PLACIDUS,
        planets=_make_planets(),
        points=_make_points(),
        angles=_make_angles(),
        houses=_make_houses(),
        aspects=[],
    )
    response = SynastryResponse(
        subject_a=chart,
        subject_b=chart,
        synastry=Synastry(
            cross_aspects=[
                CrossAspect(
                    from_a="sun",
                    to_b="moon",
                    type=AspectType.TRINE,
                    orb=2.1,
                    applying=True,
                )
            ]
        ),
    )
    dumped = response.model_dump(by_alias=True, mode="json")
    assert set(dumped["synastry"].keys()) == {"cross_aspects"}
    assert "highlights" not in dumped["synastry"]


# ---------- SkyResponse ----------


def test_sky_response_minimal_fields() -> None:
    response = SkyResponse(
        datetime_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
        planets=_make_planets(house=None),
        points=_make_points(part_of_fortune=None),
    )
    dumped = response.model_dump(by_alias=True, mode="json")
    assert dumped["datetime_utc"].startswith("2026-04-26T12:00")
    assert dumped["angles"] is None
    assert dumped["warnings"] == []


# ---------- ErrorResponse ----------


def test_error_response_shape() -> None:
    err = ErrorResponse(error="place_not_found", detail="No matches for that place.")
    assert err.model_dump() == {
        "error": "place_not_found",
        "detail": "No matches for that place.",
    }
