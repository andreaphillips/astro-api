from fastapi.testclient import TestClient

from astro_api.main import app

client = TestClient(app)


def test_healthz_returns_200_ok():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_does_not_require_auth():
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_rejects_post():
    response = client.post("/healthz")
    assert response.status_code == 405


def test_unknown_route_returns_404():
    response = client.get("/does-not-exist")
    assert response.status_code == 404
