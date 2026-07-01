# GitLab Yearly Report Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only HTTP service that reports GitLab issues and merge requests created in a given year, at project scope or instance-wide, packaged in Docker.

**Architecture:** Three layers — `gitlab_client.py` (raw REST + auth + pagination + typed errors), `reports.py` (the two `*_by_year` functions that build query params and shape output), `main.py` (FastAPI routes + input validation + error→HTTP mapping). `config.py` reads env vars at startup and fails fast.

**Tech Stack:** Python 3.12, FastAPI + uvicorn, httpx (raw REST, no `python-gitlab`), pydantic-settings, pytest + respx.

## Global Constraints

- Python 3.12.
- Read-only only — never call POST/PUT/DELETE against GitLab.
- GitLab REST API v4, base path `{GITLAB_URL}/api/v4`.
- Auth header on every GitLab request: `PRIVATE-TOKEN: <token>`.
- Instance-wide list calls MUST send `scope=all`.
- Config via env vars: `GITLAB_URL` (required), `GITLAB_TOKEN` (required), `PORT` (default 8080), `REQUEST_TIMEOUT` (default 30).
- Service listens on port 8080 in the container.
- The GitLab client is injected into the report functions (constructor injection) so logic is testable without a live GitLab.
- No emojis anywhere in code. Use `logging`, not `print`. `try/except` with specific exceptions, never bare `except`.

## File Structure

```
gitlab-yearly-report/
├── app/
│   ├── __init__.py          # empty, marks package
│   ├── config.py            # Settings (pydantic), load_settings() fail-fast
│   ├── gitlab_client.py     # GitLabClient + typed exceptions
│   ├── reports.py           # get_issues_by_year / get_merge_requests_by_year
│   └── main.py              # FastAPI app, routes, error mapping
├── tests/
│   ├── conftest.py          # sets dummy env before app import
│   ├── test_config.py
│   ├── test_gitlab_client.py
│   ├── test_reports.py
│   └── test_api.py
├── Dockerfile
├── .dockerignore
├── requirements.txt         # runtime deps
├── requirements-dev.txt     # test deps
└── README.md
```

---

### Task 1: Project scaffolding + config

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `.dockerignore`, `app/__init__.py`, `app/config.py`, `tests/__init__.py`, `tests/test_config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Settings` (pydantic model) with attributes `gitlab_url: str`, `gitlab_token: str`, `port: int = 8080`, `request_timeout: int = 30`.
  - `load_settings() -> Settings` — returns a populated `Settings`, or calls `sys.exit(1)` with a logged error if a required var is missing.

- [ ] **Step 1: Create dependency files**

`requirements.txt`:
```
fastapi==0.115.6
uvicorn[standard]==0.34.0
httpx==0.28.1
pydantic-settings==2.7.1
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest==8.3.4
respx==0.22.0
```

`.dockerignore`:
```
__pycache__/
*.pyc
tests/
docs/
.git/
.pytest_cache/
requirements-dev.txt
```

`app/__init__.py` and `tests/__init__.py`: empty files.

- [ ] **Step 2: Install dev dependencies**

Run: `pip install -r requirements-dev.txt`
Expected: installs without error.

- [ ] **Step 3: Write the failing test**

`tests/test_config.py`:
```python
import pytest

from app.config import Settings, load_settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-test")
    settings = Settings()
    assert settings.gitlab_url == "https://gitlab.example.com"
    assert settings.gitlab_token == "glpat-test"
    assert settings.port == 8080
    assert settings.request_timeout == 30


def test_load_settings_exits_when_token_missing(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        load_settings()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 5: Write minimal implementation**

`app/config.py`:
```python
import logging
import sys

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    gitlab_url: str
    gitlab_token: str
    port: int = 8080
    request_timeout: int = 30


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        logger.error("Invalid configuration, check GITLAB_URL and GITLAB_TOKEN: %s", exc)
        sys.exit(1)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt .dockerignore app/ tests/
git commit -m "feat: project scaffolding and config with fail-fast env loading"
```

---

### Task 2: GitLab client — single request, auth, typed errors

**Files:**
- Create: `app/gitlab_client.py`, `tests/test_gitlab_client.py`
- Test: `tests/test_gitlab_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - Exceptions: `GitLabError` (base), `GitLabAuthError`, `GitLabForbiddenError`, `GitLabNotFoundError`, `GitLabUpstreamError`.
  - `GitLabClient(base_url: str, token: str, timeout: int = 30)`.
  - `GitLabClient.get_all(path: str, params: dict | None = None) -> list[dict]` — added in Task 3. In this task implement `_get_page(path, params) -> tuple[list[dict], int | None]` and error mapping.

- [ ] **Step 1: Write the failing test**

`tests/test_gitlab_client.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gitlab_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.gitlab_client'`.

- [ ] **Step 3: Write minimal implementation**

`app/gitlab_client.py`:
```python
import logging

import httpx

logger = logging.getLogger(__name__)


class GitLabError(Exception):
    """Base error for GitLab client failures."""


class GitLabAuthError(GitLabError):
    """GitLab returned 401 Unauthorized."""


class GitLabForbiddenError(GitLabError):
    """GitLab returned 403 Forbidden."""


class GitLabNotFoundError(GitLabError):
    """GitLab returned 404 Not Found."""


class GitLabUpstreamError(GitLabError):
    """GitLab was unreachable or returned an unexpected status."""


class GitLabClient:
    def __init__(self, base_url: str, token: str, timeout: int = 30):
        self._base_url = base_url.rstrip("/")
        self._headers = {"PRIVATE-TOKEN": token}
        self._timeout = timeout

    def _get_page(self, path: str, params: dict):
        url = f"{self._base_url}/api/v4{path}"
        try:
            response = httpx.get(
                url, headers=self._headers, params=params, timeout=self._timeout
            )
        except httpx.RequestError as exc:
            logger.error("GitLab request to %s failed: %s", url, exc)
            raise GitLabUpstreamError(str(exc)) from exc

        self._raise_for_status(response)

        next_page_raw = response.headers.get("x-next-page", "")
        next_page = int(next_page_raw) if next_page_raw else None
        return response.json(), next_page

    @staticmethod
    def _raise_for_status(response: httpx.Response):
        status = response.status_code
        if status == 401:
            raise GitLabAuthError("GitLab authentication failed")
        if status == 403:
            raise GitLabForbiddenError("GitLab permission denied")
        if status == 404:
            raise GitLabNotFoundError("GitLab resource not found")
        if status >= 500:
            raise GitLabUpstreamError(f"GitLab returned server error {status}")
        if status >= 400:
            raise GitLabUpstreamError(f"Unexpected GitLab status {status}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gitlab_client.py -v`
Expected: PASS (6 passed — parametrize expands to 4).

- [ ] **Step 5: Commit**

```bash
git add app/gitlab_client.py tests/test_gitlab_client.py
git commit -m "feat: GitLab client single request with auth and typed errors"
```

---

### Task 3: GitLab client — pagination

**Files:**
- Modify: `app/gitlab_client.py` (add `get_all`)
- Modify: `tests/test_gitlab_client.py` (add pagination tests)

**Interfaces:**
- Consumes: `GitLabClient._get_page` from Task 2.
- Produces: `GitLabClient.get_all(path: str, params: dict | None = None) -> list[dict]` — sets `per_page=100`, loops following `X-Next-Page`, concatenates all pages.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gitlab_client.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gitlab_client.py -k get_all -v`
Expected: FAIL — `AttributeError: 'GitLabClient' object has no attribute 'get_all'`.

- [ ] **Step 3: Write minimal implementation**

Add this method to `GitLabClient` in `app/gitlab_client.py` (place it above `_get_page`):
```python
    def get_all(self, path: str, params: dict | None = None) -> list[dict]:
        merged = dict(params or {})
        merged.setdefault("per_page", 100)
        results: list[dict] = []
        page: int | None = 1
        while page is not None:
            page_params = {**merged, "page": page}
            data, page = self._get_page(path, page_params)
            results.extend(data)
        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gitlab_client.py -v`
Expected: PASS (all client tests green).

- [ ] **Step 5: Commit**

```bash
git add app/gitlab_client.py tests/test_gitlab_client.py
git commit -m "feat: GitLab client pagination via X-Next-Page"
```

---

### Task 4: Reports layer — issues and merge requests by year

**Files:**
- Create: `app/reports.py`, `tests/test_reports.py`
- Test: `tests/test_reports.py`

**Interfaces:**
- Consumes: `GitLabClient.get_all` from Task 3.
- Produces:
  - `get_issues_by_year(client, year, project_id_or_path=None) -> dict`
  - `get_merge_requests_by_year(client, year, project_id_or_path=None) -> dict`
  - Return shape: `{"year": int, "scope": str, "count": int, "items": list[dict]}`, where each item is `{"id","iid","title","author","state","created_at","web_url"}`.

- [ ] **Step 1: Write the failing test**

`tests/test_reports.py`:
```python
from app import reports


class FakeClient:
    def __init__(self, items):
        self._items = items
        self.calls = []

    def get_all(self, path, params=None):
        self.calls.append((path, params or {}))
        return self._items


RAW = [
    {
        "id": 10,
        "iid": 3,
        "title": "Bug",
        "author": {"username": "jdoe"},
        "state": "opened",
        "created_at": "2025-05-01T09:00:00Z",
        "web_url": "https://gitlab.example.com/g/p/-/issues/3",
        "extra_noise": "ignored",
    }
]


def test_issues_instance_scope_sends_scope_all_and_year_bounds():
    client = FakeClient(RAW)
    result = reports.get_issues_by_year(client, 2025)
    path, params = client.calls[0]
    assert path == "/issues"
    assert params["scope"] == "all"
    assert params["created_after"] == "2025-01-01T00:00:00Z"
    assert params["created_before"] == "2025-12-31T23:59:59Z"
    assert result["scope"] == "instance"
    assert result["year"] == 2025
    assert result["count"] == 1


def test_item_is_shaped_and_trimmed():
    client = FakeClient(RAW)
    result = reports.get_issues_by_year(client, 2025)
    item = result["items"][0]
    assert item == {
        "id": 10,
        "iid": 3,
        "title": "Bug",
        "author": "jdoe",
        "state": "opened",
        "created_at": "2025-05-01T09:00:00Z",
        "web_url": "https://gitlab.example.com/g/p/-/issues/3",
    }
    assert "extra_noise" not in item


def test_project_path_is_url_encoded_and_no_scope():
    client = FakeClient(RAW)
    result = reports.get_issues_by_year(client, 2025, "mygroup/my-project")
    path, params = client.calls[0]
    assert path == "/projects/mygroup%2Fmy-project/issues"
    assert "scope" not in params
    assert result["scope"] == "project:mygroup/my-project"


def test_numeric_project_id_used_as_is():
    client = FakeClient(RAW)
    reports.get_issues_by_year(client, 2025, 42)
    path, _ = client.calls[0]
    assert path == "/projects/42/issues"


def test_merge_requests_uses_merge_requests_resource():
    client = FakeClient(RAW)
    reports.get_merge_requests_by_year(client, 2025)
    path, _ = client.calls[0]
    assert path == "/merge_requests"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports'`.

- [ ] **Step 3: Write minimal implementation**

`app/reports.py`:
```python
from urllib.parse import quote


def _year_bounds(year: int) -> tuple[str, str]:
    return f"{year}-01-01T00:00:00Z", f"{year}-12-31T23:59:59Z"


def _encode_project(project_id_or_path) -> str:
    project = str(project_id_or_path)
    if project.isdigit():
        return project
    return quote(project, safe="")


def _shape_item(raw: dict) -> dict:
    author = raw.get("author") or {}
    return {
        "id": raw.get("id"),
        "iid": raw.get("iid"),
        "title": raw.get("title"),
        "author": author.get("username"),
        "state": raw.get("state"),
        "created_at": raw.get("created_at"),
        "web_url": raw.get("web_url"),
    }


def _report(client, resource: str, year: int, project_id_or_path) -> dict:
    created_after, created_before = _year_bounds(year)
    params = {"created_after": created_after, "created_before": created_before}

    if project_id_or_path is None:
        params["scope"] = "all"
        path = f"/{resource}"
        scope = "instance"
    else:
        path = f"/projects/{_encode_project(project_id_or_path)}/{resource}"
        scope = f"project:{project_id_or_path}"

    items = [_shape_item(raw) for raw in client.get_all(path, params=params)]
    return {"year": year, "scope": scope, "count": len(items), "items": items}


def get_issues_by_year(client, year: int, project_id_or_path=None) -> dict:
    return _report(client, "issues", year, project_id_or_path)


def get_merge_requests_by_year(client, year: int, project_id_or_path=None) -> dict:
    return _report(client, "merge_requests", year, project_id_or_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_reports.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add app/reports.py tests/test_reports.py
git commit -m "feat: reporting layer with year filtering, scope=all, project encoding"
```

---

### Task 5: FastAPI app — routes, validation, error mapping, health

**Files:**
- Create: `app/main.py`, `tests/conftest.py`, `tests/test_api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `load_settings` (Task 1), `GitLabClient` + typed errors (Tasks 2–3), `reports.get_issues_by_year` / `get_merge_requests_by_year` (Task 4).
- Produces: FastAPI `app` with `GET /health`, `GET /issues`, `GET /merge-requests`.

- [ ] **Step 1: Write conftest so app import has env**

`tests/conftest.py`:
```python
import os

os.environ.setdefault("GITLAB_URL", "https://gitlab.example.com")
os.environ.setdefault("GITLAB_TOKEN", "glpat-test")
```

- [ ] **Step 2: Write the failing test**

`tests/test_api.py`:
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 4: Write minimal implementation**

`app/main.py`:
```python
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import reports
from .config import load_settings
from .gitlab_client import (
    GitLabAuthError,
    GitLabClient,
    GitLabForbiddenError,
    GitLabNotFoundError,
    GitLabUpstreamError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = load_settings()
gitlab_client = GitLabClient(
    settings.gitlab_url, settings.gitlab_token, settings.request_timeout
)

app = FastAPI(title="GitLab Yearly Report Service")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "Invalid or missing query parameters"})


@app.get("/health")
def health():
    return {"status": "ok"}


def _run_report(report_fn, year: int, project):
    try:
        return report_fn(gitlab_client, year, project)
    except GitLabAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except GitLabForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except GitLabNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GitLabUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/issues")
def issues(year: int = Query(..., ge=1900, le=2100), project: str | None = None):
    return _run_report(reports.get_issues_by_year, year, project)


@app.get("/merge-requests")
def merge_requests(year: int = Query(..., ge=1900, le=2100), project: str | None = None):
    return _run_report(reports.get_merge_requests_by_year, year, project)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_api.py -v`
Expected: PASS (all API tests green).

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: every test across all files passes.

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/conftest.py tests/test_api.py
git commit -m "feat: FastAPI routes with validation and GitLab error mapping"
```

---

### Task 6: Dockerize

**Files:**
- Create: `Dockerfile`

**Interfaces:**
- Consumes: `app/` package, `requirements.txt`.
- Produces: an image that runs the service on port 8080.

- [ ] **Step 1: Write the Dockerfile**

`Dockerfile`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN useradd --create-home appuser
USER appuser

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

- [ ] **Step 2: Build the image**

Run: `docker build -t gitlab-yearly-report .`
Expected: build completes, image tagged.

- [ ] **Step 3: Smoke-test the container health endpoint**

Run:
```bash
docker run --rm -d --name glr-test -p 8080:8080 \
  -e GITLAB_URL="https://gitlab.example.com" \
  -e GITLAB_TOKEN="glpat-dummy" \
  gitlab-yearly-report
curl -s http://localhost:8080/health
docker stop glr-test
```
Expected: `{"status":"ok"}`.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "feat: Dockerfile for the report service"
```

---

### Task 7: README + delivery

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: documentation covering overview, config, run, curl examples, tests, the scope=all note, local GitLab playground.

- [ ] **Step 1: Write README.md**

Include these sections (full content written during execution):
- Title + one-paragraph overview (read-only GitLab yearly report service).
- Architecture: the three-layer diagram from the spec.
- Requirements: Docker, or Python 3.12 for local runs.
- Configuration table: `GITLAB_URL`, `GITLAB_TOKEN`, `PORT`, `REQUEST_TIMEOUT`.
- Example config block (env vars).
- Run with Docker: `docker build` + the `docker run` command from the assignment.
- API reference: `/health`, `/issues`, `/merge-requests` with the `year` and `project` params.
- Example curl commands:
  ```bash
  curl "http://localhost:8080/health"
  curl "http://localhost:8080/issues?year=2025"
  curl "http://localhost:8080/issues?year=2025&project=mygroup%2Fmy-project"
  curl "http://localhost:8080/merge-requests?year=2025"
  curl "http://localhost:8080/merge-requests?year=2025&project=42"
  ```
- Running tests: `pip install -r requirements-dev.txt && pytest -v`.
- Design note: why `scope=all` matters (default is `created_by_me`, which under-reports instance-wide).
- Design note: raw REST chosen over `python-gitlab` to make the API interaction explicit; client injected for testability.
- Local GitLab playground: the `docker run gitlab/gitlab-ee` snippet from the assignment, plus "create a group/project/issues/MR, then a read-scoped token."

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, curl examples, and design notes"
```

- [ ] **Step 3: Push to a public GitHub repo (final delivery)**

```bash
git remote add origin https://github.com/<user>/gitlab-yearly-report.git
git branch -M main
git push -u origin main
```
Then submit the repository URL.

---

## Notes on testing against a live GitLab (after Task 5)

The unit suite proves all logic with mocked GitLab. To validate end-to-end,
start the local GitLab 18.10+ container from the assignment, create a group,
project, a few issues and MRs, generate a read-scoped token, then run the
service pointed at it and hit the curl commands. This is optional for the code
to be correct but recommended before submitting.
