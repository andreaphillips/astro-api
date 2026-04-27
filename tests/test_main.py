from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from astro_api import geocoding
from astro_api import main as main_module
from astro_api.charts import DateOutOfRange
from astro_api.geocoding import (
    GeocodingTimeout,
    PlaceNotFound,
    ResolvedLocation,
)
from astro_api.main import app

API_KEY = "test-secret"

ANDREA_PLACE = "Maracaibo, Venezuela"
ANDREA_LOCATION = ResolvedLocation(
    latitude=10.66,
    longitude=-71.65,
    timezone="America/Caracas",
)
ANDREA_PAYLOAD = {
    "subject": {
        "name": "Andrea",
        "birth_date": "1989-05-12",
        "birth_time": "14:30",
        "birth_place": ANDREA_PLACE,
    }
}

# Second subject for synastry tests — keep simple, mock locations regardless.
SISTER_PLACE = "Caracas, Venezuela"
SISTER_LOCATION = ResolvedLocation(
    latitude=10.5,
    longitude=-66.9,
    timezone="America/Caracas",
)
SYNASTRY_PAYLOAD = {
    "subject_a": ANDREA_PAYLOAD["subject"],
    "subject_b": {
        "name": "Sister",
        "birth_date": "1992-08-03",
        "birth_time": "06:15",
        "birth_place": SISTER_PLACE,
    },
}


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
    mapping = mapping or {ANDREA_PLACE: ANDREA_LOCATION, SISTER_PLACE: SISTER_LOCATION}

    def fake(place: str) -> ResolvedLocation:
        if side_effect is not None:
            raise side_effect
        return mapping[place]

    mock = MagicMock(side_effect=fake)
    monkeypatch.setattr(main_module, "resolve_place", mock)
    return mock


# ---------- Auth gating on /v1/* ----------


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/v1/natal", ANDREA_PAYLOAD),
        ("post", "/v1/transits", {"natal_subject": ANDREA_PAYLOAD["subject"]}),
        ("post", "/v1/synastry", SYNASTRY_PAYLOAD),
        ("get", "/v1/sky", None),
    ],
)
def test_v1_endpoints_require_api_key(
    client: TestClient, method: str, path: str, body: Any
) -> None:
    response = client.post(path, json=body) if method == "post" else client.get(path)
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"] == "unauthorized"


def test_wrong_api_key_returns_401(client: TestClient) -> None:
    response = client.post("/v1/natal", json=ANDREA_PAYLOAD, headers={"X-API-Key": "nope"})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


# ---------- Happy paths ----------


def test_post_natal_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/natal",
        json=ANDREA_PAYLOAD,
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["house_system"] == "placidus"
    assert body["subject"]["timezone"] == "America/Caracas"
    assert body["subject"]["datetime_utc"].startswith("1989-05-12T18:30:00")
    assert set(body["planets"].keys()) >= {"sun", "moon", "mercury"}
    assert body["warnings"] == []


def test_post_transits_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/transits",
        json={
            "natal_subject": ANDREA_PAYLOAD["subject"],
            "target_date": "2026-04-26T12:00:00Z",
        },
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "transits" in body
    assert isinstance(body["transits"], list)


def test_post_synastry_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch)
    response = client.post(
        "/v1/synastry",
        json=SYNASTRY_PAYLOAD,
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subject_a"]["subject"]["name"] == "Andrea"
    assert body["subject_b"]["subject"]["name"] == "Sister"
    assert "cross_aspects" in body["synastry"]


def test_get_sky_happy_path(client: TestClient) -> None:
    response = client.get(
        "/v1/sky",
        params={"date_time": "2026-04-26T12:00:00Z"},
        headers={"X-API-Key": API_KEY},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["datetime_utc"].startswith("2026-04-26T12:00:00")
    assert body["angles"] is None
    assert "sun" in body["planets"]


def test_get_sky_defaults_to_now(client: TestClient) -> None:
    before = datetime.now(UTC)
    response = client.get("/v1/sky", headers={"X-API-Key": API_KEY})
    assert response.status_code == 200
    body = response.json()
    parsed = datetime.fromisoformat(body["datetime_utc"].replace("Z", "+00:00"))
    assert (parsed - before).total_seconds() < 60


# ---------- Geocoding warnings surface inline ----------


def test_multiple_matches_warning_surfaced_in_natal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ambiguous = ResolvedLocation(
        latitude=10.66,
        longitude=-71.65,
        timezone="America/Caracas",
        warnings=("multiple_matches",),
    )
    _patch_resolve(monkeypatch, {ANDREA_PLACE: ambiguous})
    response = client.post("/v1/natal", json=ANDREA_PAYLOAD, headers={"X-API-Key": API_KEY})
    assert response.status_code == 200, response.text
    assert "multiple_matches" in response.json()["warnings"]


def test_multiple_matches_warning_surfaced_per_synastry_subject(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ambiguous_a = ResolvedLocation(
        latitude=10.66,
        longitude=-71.65,
        timezone="America/Caracas",
        warnings=("multiple_matches",),
    )
    _patch_resolve(monkeypatch, {ANDREA_PLACE: ambiguous_a, SISTER_PLACE: SISTER_LOCATION})
    response = client.post("/v1/synastry", json=SYNASTRY_PAYLOAD, headers={"X-API-Key": API_KEY})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "multiple_matches" in body["subject_a"]["warnings"]
    assert "multiple_matches" not in body["subject_b"]["warnings"]


# ---------- Typed exceptions → spec §7 envelope ----------


def test_place_not_found_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, side_effect=PlaceNotFound("nowhereville"))
    response = client.post("/v1/natal", json=ANDREA_PAYLOAD, headers={"X-API-Key": API_KEY})
    assert response.status_code == 422
    assert response.json()["error"] == "place_not_found"


def test_geocoding_timeout_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, side_effect=GeocodingTimeout("timed out"))
    response = client.post("/v1/natal", json=ANDREA_PAYLOAD, headers={"X-API-Key": API_KEY})
    assert response.status_code == 503
    assert response.json()["error"] == "geocoding_unavailable"


def test_date_out_of_range_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch)

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise DateOutOfRange("ephemeris range")

    monkeypatch.setattr(main_module, "build_natal", boom)
    response = client.post("/v1/natal", json=ANDREA_PAYLOAD, headers={"X-API-Key": API_KEY})
    assert response.status_code == 422
    assert response.json()["error"] == "date_out_of_range"


def test_unhandled_exception_returns_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolve(monkeypatch)

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(main_module, "build_natal", boom)
    # TestClient re-raises by default; suppress to verify response envelope.
    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.post("/v1/natal", json=ANDREA_PAYLOAD, headers={"X-API-Key": API_KEY})
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"


# ---------- OpenAPI security scheme + global apply rule ----------


def test_openapi_defines_apikey_security_scheme(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["ApiKeyAuth"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }


def test_openapi_applies_security_to_v1_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for path in ("/v1/natal", "/v1/transits", "/v1/synastry", "/v1/sky"):
        for op in paths[path].values():
            assert op["security"] == [{"ApiKeyAuth": []}], f"missing security on {path}"


def test_openapi_excludes_healthz_and_openapi_from_security(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    healthz_op = next(iter(schema["paths"]["/healthz"].values()))
    assert "security" not in healthz_op
    # /openapi.json isn't registered as a route, so it never appears in paths
    assert "/openapi.json" not in schema["paths"]


def test_openapi_metadata(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "astro-api"
    assert schema["info"]["version"] == "1.0.0"
    assert "Western astrology" in schema["info"]["description"]


# ---------- Logging middleware ----------


def test_logging_middleware_emits_json(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_resolve(monkeypatch)
    client.post("/v1/natal", json=ANDREA_PAYLOAD, headers={"X-API-Key": API_KEY})
    captured = capsys.readouterr().out.strip().splitlines()
    last_line = captured[-1]
    import json as _json

    payload = _json.loads(last_line)
    assert payload["method"] == "POST"
    assert payload["path"] == "/v1/natal"
    assert payload["status"] == 200
    assert isinstance(payload["latency_ms"], float)
    assert "error_code" not in payload


def test_logging_middleware_records_error_code(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_resolve(monkeypatch, side_effect=PlaceNotFound("nowhere"))
    client.post("/v1/natal", json=ANDREA_PAYLOAD, headers={"X-API-Key": API_KEY})
    last_line = capsys.readouterr().out.strip().splitlines()[-1]
    import json as _json

    payload = _json.loads(last_line)
    assert payload["status"] == 422
    assert payload["error_code"] == "place_not_found"
