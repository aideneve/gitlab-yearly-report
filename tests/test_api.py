import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

BASE = "https://gitlab.example.com"
client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_year_returns_400():
    assert client.get("/issues").status_code == 400


def test_invalid_year_returns_400():
    assert client.get("/issues", params={"year": "notayear"}).status_code == 400


@respx.mock
def test_issues_happy_path():
    respx.get(f"{BASE}/api/v4/issues").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": 1, "iid": 1, "title": "x", "author": {"username": "a"},
                   "state": "opened", "created_at": "2025-01-02T00:00:00Z",
                   "web_url": "http://x"}],
            headers={"X-Next-Page": ""},
        )
    )
    response = client.get("/issues", params={"year": 2025})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["scope"] == "instance"


@respx.mock
def test_gitlab_401_maps_to_401():
    respx.get(f"{BASE}/api/v4/issues").mock(return_value=httpx.Response(401))
    assert client.get("/issues", params={"year": 2025}).status_code == 401


@respx.mock
def test_gitlab_403_maps_to_403():
    respx.get(f"{BASE}/api/v4/issues").mock(return_value=httpx.Response(403))
    assert client.get("/issues", params={"year": 2025}).status_code == 403


@respx.mock
def test_gitlab_404_maps_to_404():
    respx.get(f"{BASE}/api/v4/projects/99/issues").mock(
        return_value=httpx.Response(404)
    )
    assert client.get(
        "/issues", params={"year": 2025, "project": "99"}
    ).status_code == 404


@respx.mock
def test_gitlab_500_maps_to_502():
    respx.get(f"{BASE}/api/v4/issues").mock(return_value=httpx.Response(500))
    assert client.get("/issues", params={"year": 2025}).status_code == 502
