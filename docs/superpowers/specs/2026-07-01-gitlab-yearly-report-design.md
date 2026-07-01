# Design: GitLab Yearly Report Service

Mobileye DevOps-IT home assignment. A read-only HTTP service that reports GitLab
issues and merge requests created in a given year, at either project scope or
instance-wide scope. Packaged in a Docker container.

**Strictly read-only.** The service never creates, updates, or deletes GitLab
resources.

## Stack

- Python 3.12
- FastAPI (web framework) + uvicorn (server)
- httpx (raw GitLab REST calls — no `python-gitlab` library, so the REST
  interaction is explicit and explainable)
- pytest + respx (tests with mocked GitLab HTTP)

Rationale: FastAPI gives automatic input validation (covers the 400 error cases),
typed exception handling, and a built-in interactive docs page at `/docs`. Using
raw REST instead of a client library is a deliberate choice — the assignment is
about demonstrating understanding of the GitLab REST API (auth, pagination,
query params, scope), which a library would hide.

## Architecture

Three layers, each with a single responsibility so each is independently testable:

```
HTTP request
   │
   ▼
main.py           FastAPI routes, input validation, maps errors -> HTTP status codes
   │
   ▼
reports.py        get_issues_by_year() / get_merge_requests_by_year():
   │              builds query params, shapes the response envelope
   ▼
gitlab_client.py  raw GitLab REST calls: auth header, pagination loop,
   │              raises typed errors (no knowledge of HTTP status codes)
   ▼
GitLab REST API v4
```

`config.py` reads env vars once at startup and fails fast if a required var is
missing.

Why this split: tests mock `gitlab_client` to test `reports` logic in isolation,
and mock GitLab's HTTP to test the routes. The data flow reads top-to-bottom.

## Project layout

```
gitlab-yearly-report/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app + routes + error mapping
│   ├── gitlab_client.py # HTTP calls, auth, pagination, typed errors
│   ├── reports.py       # get_issues_by_year / get_merge_requests_by_year + shaping
│   └── config.py        # reads GITLAB_URL / GITLAB_TOKEN, fails fast
├── tests/
├── docs/
├── Dockerfile
├── requirements.txt
└── README.md
```

## Core functions

```python
get_issues_by_year(year, project_id_or_path=None) -> dict
get_merge_requests_by_year(year, project_id_or_path=None) -> dict
```

Both return a summary envelope:

```json
{
  "year": 2025,
  "scope": "instance",
  "count": 142,
  "items": [
    {
      "id": 12,
      "iid": 4,
      "title": "Example issue",
      "author": "jdoe",
      "state": "opened",
      "created_at": "2025-03-01T10:00:00.000Z",
      "web_url": "https://gitlab.example.com/mygroup/my-project/-/issues/4"
    }
  ]
}
```

`scope` is `"instance"` when no project is given, or `"project:<id-or-path>"`
when scoped to one project.

## GitLab interaction details

- **Auth:** every request sends header `PRIVATE-TOKEN: <token>`. Works for both
  personal access tokens and project access tokens.
- **Year -> date filter:** for year `Y`, send
  `created_after=Y-01-01T00:00:00Z` and `created_before=Y-12-31T23:59:59Z`.
  Filtering happens server-side on GitLab, so we do not download the whole
  instance and filter locally.
- **Scope (the key subtlety):** instance-wide calls always send `scope=all`.
  GitLab's `/issues` and `/merge_requests` endpoints default to
  `created_by_me`, which would silently return only items the token's own user
  created. `scope=all` returns everything the token is permitted to see, which
  is the correct reading of "entire GitLab instance, according to the
  permissions of the provided token." Project-scoped calls hit
  `/projects/{id}/issues` and do not need this param.
- **Project id/path:** a numeric id is used as-is; a path like
  `mygroup/my-project` is URL-encoded to `mygroup%2Fmy-project`. The client
  handles encoding.
- **Pagination:** request `per_page=100`, then loop following the
  `X-Next-Page` response header until it is empty. Without this the service
  would only return the first page.

## API endpoints

| Method | Path | Behavior |
|---|---|---|
| GET | `/health` | Returns `{"status": "ok"}`. Never touches GitLab. |
| GET | `/issues?year=YYYY[&project=...]` | Issues report. |
| GET | `/merge-requests?year=YYYY[&project=...]` | Merge requests report. |

`project` accepts a numeric id or a URL-encoded path. Omitting it means
instance-wide.

## Error handling

| Situation | Response |
|---|---|
| `year` missing | 400 Bad Request (FastAPI validation) |
| `year` not a valid 4-digit year (range 1900–2100) | 400 Bad Request |
| `GITLAB_TOKEN` missing | Fail fast at startup: clear log message + non-zero exit |
| GitLab returns 401 | 401 Unauthorized |
| GitLab returns 403 | 403 Forbidden |
| GitLab returns 404 (project not found) | 404 Not Found |
| GitLab unreachable / 5xx | 502 Bad Gateway |

`gitlab_client` raises typed exceptions (`GitLabAuthError`,
`GitLabForbiddenError`, `GitLabNotFoundError`, `GitLabUpstreamError`);
`main.py` catches them and maps to the HTTP status. The client itself knows
nothing about HTTP status codes.

## Configuration (environment variables)

| Var | Required | Default |
|---|---|---|
| `GITLAB_URL` | yes | — |
| `GITLAB_TOKEN` | yes | — |
| `PORT` | no | 8080 |
| `REQUEST_TIMEOUT` | no | 30 (seconds) |

Read via Pydantic `BaseSettings`. A missing required var causes a loud startup
failure rather than a confusing runtime error.

## Testing

pytest + respx (mocks httpx requests), driving routes with FastAPI's
`TestClient`. No live GitLab required — the logic is proven before the heavy
local GitLab container is even started.

Cases:
- year -> `created_after` / `created_before` param construction
- pagination across multiple pages (follows `X-Next-Page`)
- instance-wide calls send `scope=all`
- project path is URL-encoded correctly
- error mapping: GitLab 401/403/404 -> 401/403/404, upstream failure -> 502
- input validation: missing year -> 400, non-numeric / out-of-range year -> 400
- `/health` returns `{"status": "ok"}`

## Docker

- Base image `python:3.12-slim`
- Runs as a non-root user
- Installs `requirements.txt`, copies `app/`
- `EXPOSE 8080`
- `CMD` runs `uvicorn app.main:app --host 0.0.0.0 --port 8080`

Run:

```
docker run --rm -p 8080:8080 \
  -e GITLAB_URL="https://gitlab.example.com" \
  -e GITLAB_TOKEN="glpat-xxxx" \
  gitlab-yearly-report
```

## README contents

- Overview + architecture diagram
- Environment variable reference and example config
- `docker build` / `docker run` instructions
- Example `curl` commands for every endpoint
- How to run the tests
- Explanation of the `scope=all` behavior
- Local GitLab 18.10+ playground setup instructions

## Delivery

`git init` in the project folder now (so the design and code are versioned);
push to a public GitHub repository at the end and submit the URL.

## Out of scope

- MCP server (bonus task) — deferred, not part of this build.
- Any write operations against GitLab.
