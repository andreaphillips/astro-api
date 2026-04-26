import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from astro_api.auth import require_api_key
from astro_api.main import app as real_app
from astro_api.main import http_exception_handler
from astro_api.settings import get_settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ASTRO_API_KEY", "secret-123")
    get_settings.cache_clear()

    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)

    @app.get("/protected")
    def _protected(_: None = Depends(require_api_key)) -> dict[str, str]:
        return {"ok": "true"}

    return TestClient(app)


def test_missing_header_returns_401_envelope(client: TestClient) -> None:
    response = client.get("/protected")
    assert response.status_code == 401
    body = response.json()
    assert body == {"error": "unauthorized", "detail": "Missing X-API-Key header."}


def test_wrong_key_returns_401_envelope(client: TestClient) -> None:
    response = client.get("/protected", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401
    body = response.json()
    assert body == {"error": "unauthorized", "detail": "Invalid X-API-Key."}


def test_correct_key_passes_through(client: TestClient) -> None:
    response = client.get("/protected", headers={"X-API-Key": "secret-123"})
    assert response.status_code == 200
    assert response.json() == {"ok": "true"}


def test_header_alias_is_case_insensitive(client: TestClient) -> None:
    response = client.get("/protected", headers={"x-api-key": "secret-123"})
    assert response.status_code == 200


def test_empty_header_value_returns_401(client: TestClient) -> None:
    response = client.get("/protected", headers={"X-API-Key": ""})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_healthz_remains_unprotected_on_real_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTRO_API_KEY", "secret-123")
    get_settings.cache_clear()
    real_client = TestClient(real_app)
    response = real_client.get("/healthz")
    assert response.status_code == 200
