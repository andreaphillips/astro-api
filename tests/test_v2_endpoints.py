"""Integration tests for the Phase 2 endpoints: /v1/solar-return and
/v1/progressions. Mirrors the fixtures and conventions of test_main.py."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from astro_api import geocoding
from astro_api import main as main_module
from astro_api.geocoding import PlaceNotFound, ResolvedLocation
from astro_api.main import app

API_KEY = "test-secret"

BIRTH_PLACE = "San José, Costa Rica"
BIRTH_LOCATION = ResolvedLocation(latitude=9.93, longitude=-84.08, timezone="America/Costa_Rica")

RELOCATION_PLACE = "Tamarindo, Costa Rica"
RELOCATION = ResolvedLocation(latitude=10.30, longitude=-85.84, timezone="America/Costa_Rica")

SUBJECT = {
    "name": "Andrea",
    "birth_date": "1980-12-09",
    "birth_time": "10:35",
    "birth_place": BIRTH_PLACE,
}
SUBJECT_NO_TIME = {
    "name": "Andrea",
    "birth_date": "1980-12-09",
    "birth_place": BIRTH_PLACE,
}

SOLAR_RETURN_PAYLOAD = {"subject": SUBJECT, "year": 2026}
PROGRESSIONS_PAYLOAD = {"subject": SUBJECT, "target_date": "2026-04-27"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ASTRO_API_KEY", API_KEY)
    from astro_api.settings import get_settings

    get_settings.cache_clear()
    geocoding.resolve_place.cache_clear()
    main_module.app.openapi_schema = None  # force regeneration per test
    return TestClient(app)


def _patch_resolve(
    monkeypatch: pytest.MonkeyPatch,
    mapping: dict[str, ResolvedLocation] | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Stub geocoding.resolve_place at the use-site (astro_api.main)."""
    mapping = mapping or {BIRTH_PLACE: BIRTH_LOCATION, RELOCATION_PLACE: RELOCATION}

    def fake(place: str) -> ResolvedLocation:
        if side_effect is not None:
            raise side_effect
        return mapping[place]

    mock = MagicMock(side_effect=fake)
    monkeypatch.setattr(main_module, "resolve_place", mock)
    return mock


# ---------- Auth gating ----------


@pytest.mark.parametrize(
    "path,body",
    [
        ("/v1/solar-return", SOLAR_RETURN_PAYLOAD),
        ("/v1/progressions", PROGRESSIONS_PAYLOAD),
    ],
)
def test_endpoints_require_api_key(client: TestClient, path: str, body: Any) -> None:
    response = client.post(path, json=body)
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


# ---------- /v1/solar-return ----------


def test_solar_return_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/solar-return", json=SOLAR_RETURN_PAYLOAD, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["relocated"] is False
    assert body["house_system"] == "placidus"
    assert "return_moment" in body
    assert body["return_moment"]["datetime_utc"].startswith("2026-")
    # No relocation -> return_moment reflects the birth location.
    assert body["return_moment"]["latitude"] == BIRTH_LOCATION.latitude
    assert body["return_moment"]["timezone"] == "America/Costa_Rica"
    # Subject block reports the natal location.
    assert body["subject"]["latitude"] == BIRTH_LOCATION.latitude
    assert set(body["planets"].keys()) >= {"sun", "moon", "mercury"}
    assert body["warnings"] == []


def test_solar_return_relocation(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/solar-return",
        json={**SOLAR_RETURN_PAYLOAD, "relocation_place": RELOCATION_PLACE},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["relocated"] is True
    assert body["return_moment"]["latitude"] == RELOCATION.latitude
    assert body["return_moment"]["longitude"] == RELOCATION.longitude
    # Subject block still reports the natal location, not the relocation.
    assert body["subject"]["latitude"] == BIRTH_LOCATION.latitude


def test_solar_return_missing_birth_time_returns_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/solar-return",
        json={"subject": SUBJECT_NO_TIME, "year": 2026},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "birth_time_required_for_solar_return"


def test_solar_return_bad_birth_place_returns_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolve(monkeypatch, side_effect=PlaceNotFound("nowhereville"))
    response = client.post(
        "/v1/solar-return", json=SOLAR_RETURN_PAYLOAD, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422
    assert response.json()["error"] == "place_not_found"


def test_solar_return_bad_relocation_place_returns_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Birth place resolves, relocation place does not.
    def fake(place: str) -> ResolvedLocation:
        if place == BIRTH_PLACE:
            return BIRTH_LOCATION
        raise PlaceNotFound(place)

    monkeypatch.setattr(main_module, "resolve_place", MagicMock(side_effect=fake))
    response = client.post(
        "/v1/solar-return",
        json={**SOLAR_RETURN_PAYLOAD, "relocation_place": "Nowhereville"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "place_not_found"


def test_solar_return_multiple_matches_warning_surfaced(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ambiguous = ResolvedLocation(
        latitude=9.93,
        longitude=-84.08,
        timezone="America/Costa_Rica",
        warnings=("multiple_matches",),
    )
    _patch_resolve(monkeypatch, {BIRTH_PLACE: ambiguous})
    response = client.post(
        "/v1/solar-return", json=SOLAR_RETURN_PAYLOAD, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 200, response.text
    assert "multiple_matches" in response.json()["warnings"]


# ---------- /v1/progressions ----------


def test_progressions_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/progressions", json=PROGRESSIONS_PAYLOAD, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target_date"] == "2026-04-27"
    assert body["house_system"] == "placidus"
    assert "progressed_datetime_utc" in body
    # natal block carries houses; progressed block does not.
    assert body["natal"]["houses"] is not None and len(body["natal"]["houses"]) == 12
    assert "houses" not in body["progressed"]
    assert "progressed_aspects" in body
    assert body["warnings"] == []


def test_progressions_target_date_optional(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/progressions", json={"subject": SUBJECT}, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 200, response.text
    assert response.json()["target_date"] is not None


def test_progressions_aspects_sorted_by_orb(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/progressions", json=PROGRESSIONS_PAYLOAD, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 200, response.text
    orbs = [a["orb"] for a in response.json()["progressed_aspects"]]
    assert orbs == sorted(orbs)


def test_progressions_missing_birth_time_returns_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/progressions",
        json={"subject": SUBJECT_NO_TIME, "target_date": "2026-04-27"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "birth_time_required_for_progressions"


def test_progressions_bad_birth_place_returns_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolve(monkeypatch, side_effect=PlaceNotFound("nowhereville"))
    response = client.post(
        "/v1/progressions", json=PROGRESSIONS_PAYLOAD, headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422
    assert response.json()["error"] == "place_not_found"


# ---------- OpenAPI surface (spec §9.7) ----------


def test_openapi_lists_both_endpoints_with_security_and_clean_operation_ids(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    expected_ops = {
        "/v1/solar-return": "post_solar_return",
        "/v1/progressions": "post_progressions",
    }
    for path, operation_id in expected_ops.items():
        assert path in paths, f"{path} missing from OpenAPI"
        op = paths[path]["post"]
        assert op["operationId"] == operation_id
        assert op["security"] == [{"ApiKeyAuth": []}]
