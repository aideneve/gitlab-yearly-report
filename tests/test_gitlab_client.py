import httpx
import pytest
import respx

from app.gitlab_client import (
    GitLabAuthError,
    GitLabClient,
    GitLabForbiddenError,
    GitLabNotFoundError,
    GitLabUpstreamError,
)

BASE = "https://gitlab.example.com"


def make_client():
    return GitLabClient(BASE, "glpat-test", timeout=5)


@respx.mock
def test_get_page_sends_token_and_returns_data():
    route = respx.get(f"{BASE}/api/v4/issues").mock(
        return_value=httpx.Response(200, json=[{"id": 1}], headers={"X-Next-Page": ""})
    )
    data, next_page = make_client()._get_page("/issues", {"page": 1})
    assert data == [{"id": 1}]
    assert next_page is None
    assert route.calls.last.request.headers["PRIVATE-TOKEN"] == "glpat-test"


@respx.mock
@pytest.mark.parametrize(
    "status,exc",
    [
        (401, GitLabAuthError),
        (403, GitLabForbiddenError),
        (404, GitLabNotFoundError),
        (500, GitLabUpstreamError),
    ],
)
def test_error_status_raises_typed_exception(status, exc):
    respx.get(f"{BASE}/api/v4/issues").mock(return_value=httpx.Response(status))
    with pytest.raises(exc):
        make_client()._get_page("/issues", {"page": 1})


@respx.mock
def test_connection_error_raises_upstream():
    respx.get(f"{BASE}/api/v4/issues").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(GitLabUpstreamError):
        make_client()._get_page("/issues", {"page": 1})


@respx.mock
def test_get_all_follows_pagination():
    respx.get(f"{BASE}/api/v4/issues", params={"page": "1"}).mock(
        return_value=httpx.Response(200, json=[{"id": 1}], headers={"X-Next-Page": "2"})
    )
    respx.get(f"{BASE}/api/v4/issues", params={"page": "2"}).mock(
        return_value=httpx.Response(200, json=[{"id": 2}], headers={"X-Next-Page": ""})
    )
    result = make_client().get_all("/issues")
    assert [item["id"] for item in result] == [1, 2]


@respx.mock
def test_get_all_sets_per_page_100():
    route = respx.get(f"{BASE}/api/v4/issues").mock(
        return_value=httpx.Response(200, json=[], headers={"X-Next-Page": ""})
    )
    make_client().get_all("/issues")
    assert route.calls.last.request.url.params["per_page"] == "100"
