# GitLab Yearly Report Service

A small, **read-only** HTTP service that reports GitLab **issues** and **merge
requests** created in a given year. It works at two scopes:

- a single GitLab project, or
- the entire GitLab instance (limited to what the provided token can see).

Built for the Mobileye DevOps-IT home assignment. The service never creates,
updates, or deletes anything in GitLab.

## Contents

- [Architecture](#architecture)
- [Requirements](#requirements)
- [Configuration](#configuration)
- [Run with Docker](#run-with-docker)
- [Run locally (without Docker)](#run-locally-without-docker)
- [API reference](#api-reference)
- [Example curl commands](#example-curl-commands)
- [Running the tests](#running-the-tests)
- [MCP server (bonus)](#mcp-server-bonus)
- [Design notes](#design-notes)
- [Local GitLab playground](#local-gitlab-playground)

## Architecture

Three layers, each with one responsibility, so each can be tested in isolation:

```
HTTP request
   |
   v
app/main.py           FastAPI routes, input validation, maps errors -> HTTP status codes
   |
   v
app/reports.py        get_issues_by_year() / get_merge_requests_by_year():
   |                  builds query params, shapes the response envelope
   v
app/gitlab_client.py  raw GitLab REST calls: auth header, pagination loop,
   |                  raises typed errors (knows nothing about HTTP status codes)
   v
GitLab REST API v4
```

`app/config.py` reads configuration from environment variables once at startup
and fails fast if a required variable is missing.

## Requirements

- To run the container: Docker.
- To run or test locally: Python 3.12+.

## Configuration

The service is configured entirely through environment variables.

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITLAB_URL` | yes | — | Base URL of the GitLab instance, e.g. `https://gitlab.com` |
| `GITLAB_TOKEN` | yes | — | Personal or project access token with read permissions |
| `PORT` | no | `8080` | Port the service listens on |
| `REQUEST_TIMEOUT` | no | `30` | Per-request timeout to GitLab, in seconds |

The token needs read access to the projects, issues, and merge requests you want
to report on. On GitLab this means a token with the `read_api` scope.

If `GITLAB_URL` or `GITLAB_TOKEN` is missing, the service logs a clear error and
exits immediately instead of starting in a broken state.

Example configuration:

```bash
export GITLAB_URL="https://gitlab.com"
export GITLAB_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx"
```

## Run with Docker

Build the image:

```bash
docker build -t gitlab-yearly-report .
```

Run it:

```bash
docker run --rm -p 8080:8080 \
  -e GITLAB_URL="https://gitlab.com" \
  -e GITLAB_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx" \
  gitlab-yearly-report
```

The service is then available at `http://localhost:8080`.

## Run locally (without Docker)

```bash
python -m venv .venv
source .venv/Scripts/activate          # Windows (Git Bash)
# source .venv/bin/activate            # Linux / macOS
pip install -r requirements.txt
export GITLAB_URL="https://gitlab.com"
export GITLAB_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx"
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Interactive API docs (Swagger UI) are served at `http://localhost:8080/docs`.

## API reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check. Returns `{"status": "ok"}`. Does not call GitLab. |
| GET | `/issues?year=YYYY` | Issues created in `YYYY` across the whole instance. |
| GET | `/issues?year=YYYY&project=<id-or-path>` | Issues created in `YYYY` in one project. |
| GET | `/merge-requests?year=YYYY` | Merge requests created in `YYYY` across the whole instance. |
| GET | `/merge-requests?year=YYYY&project=<id-or-path>` | Merge requests created in `YYYY` in one project. |

`project` accepts either a numeric project ID (e.g. `42`) or a URL-encoded path
(e.g. `mygroup%2Fmy-project`). Omitting `project` selects the whole instance.

Response shape:

```json
{
  "year": 2025,
  "scope": "instance",
  "count": 2,
  "items": [
    {
      "id": 101,
      "iid": 7,
      "title": "Fix login redirect",
      "author": "jdoe",
      "state": "opened",
      "created_at": "2025-03-14T09:12:00.000Z",
      "web_url": "https://gitlab.com/mygroup/my-project/-/issues/7"
    }
  ]
}
```

`scope` is `"instance"` for instance-wide reports, or `"project:<id-or-path>"`
for a single project.

### Error responses

| Situation | Status |
|---|---|
| `year` missing | 400 Bad Request |
| `year` not a valid year (must be 1900–2100) | 400 Bad Request |
| `GITLAB_TOKEN` missing | Service fails to start (clear log + non-zero exit) |
| GitLab authentication failed | 401 Unauthorized |
| GitLab permission denied | 403 Forbidden |
| GitLab project not found | 404 Not Found |
| GitLab unreachable or server error | 502 Bad Gateway |

## Example curl commands

```bash
# Health check
curl "http://localhost:8080/health"

# Issues for 2025, entire instance
curl "http://localhost:8080/issues?year=2025"

# Issues for 2025, single project by URL-encoded path (mygroup/my-project)
curl "http://localhost:8080/issues?year=2025&project=mygroup%2Fmy-project"

# Issues for 2025, single project by numeric ID
curl "http://localhost:8080/issues?year=2025&project=42"

# Merge requests for 2025, entire instance
curl "http://localhost:8080/merge-requests?year=2025"

# Merge requests for 2025, single project by numeric ID
curl "http://localhost:8080/merge-requests?year=2025&project=42"

# Missing year -> 400
curl -i "http://localhost:8080/issues"
```

## Running the tests

The test suite mocks GitLab's HTTP responses, so no live GitLab is required.

```bash
pip install -r requirements-dev.txt
pytest -v
```

Coverage includes: year-to-date parameter construction, pagination across
multiple pages, the `scope=all` behavior, project-path URL encoding, error
mapping (401/403/404/502), input validation (missing/invalid year), and the
health endpoint.

## MCP server (bonus)

In addition to the HTTP API, the same two functions are exposed as tools over
the Model Context Protocol (MCP), so an MCP-aware client (such as Claude
Desktop) can call them directly.

Required MCP tools:

- `get_issues_by_year(year, project=None)`
- `get_merge_requests_by_year(year, project=None)`

The MCP server reuses the exact same reporting logic (`app/reports.py`) and
configuration as the web service, so it reads `GITLAB_URL` and `GITLAB_TOKEN`
from the environment the same way. It communicates over stdio.

Install its dependencies (kept separate from the web service so each stays
lean):

```bash
pip install -r requirements-mcp.txt
```

Run it directly:

```bash
export GITLAB_URL="https://gitlab.com"
export GITLAB_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx"
python -m app.mcp_server
```

Test it interactively with the MCP Inspector (requires Node.js):

```bash
npx @modelcontextprotocol/inspector python -m app.mcp_server
```

Register it with an MCP client (for example Claude Desktop's
`claude_desktop_config.json`). Use absolute paths, and point `command` at the
project's virtual-environment Python:

```json
{
  "mcpServers": {
    "gitlab-yearly-report": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/gitlab-yearly-report",
      "env": {
        "GITLAB_URL": "https://gitlab.com",
        "GITLAB_TOKEN": "glpat-xxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

## Design notes

**Why `scope=all` matters.** GitLab's instance-wide `/issues` and
`/merge_requests` endpoints default their `scope` parameter to `created_by_me`,
which returns only items created by the token's own user. To report on the
entire instance "according to the permissions of the provided token," the
service explicitly sends `scope=all`. Without this, instance-wide reports would
silently under-report.

**Instance-wide scope on GitLab.com vs self-hosted.** The instance-wide
`scope=all` query is designed for a self-hosted instance (the assignment's
GitLab 18.10 playground), where it returns everything the token may see almost
instantly. On GitLab.com the same query asks GitLab to scan issues across the
entire public instance and hits GitLab.com's statement-timeout guard, returning
`500`, which this service faithfully surfaces as `502 Bad Gateway`. This is a
GitLab.com scale limitation, not a defect in the service. Project-scoped
reports (`?project=...`) work identically on both GitLab.com and self-hosted.
Validate instance-wide reporting against a self-hosted instance.

**Raw REST instead of a client library.** The service calls the GitLab REST API
directly with `httpx` rather than using the `python-gitlab` library. This keeps
the interaction with the API explicit — authentication, pagination, and query
parameters are all visible in `app/gitlab_client.py` — which is the point of the
assignment.

**Dependency injection for testability.** The report functions receive a
`GitLabClient` as an argument rather than constructing one internally. Tests
pass a fake client and verify the request-building and shaping logic without any
network calls.

**Year filtering happens server-side.** For year `Y`, the service sends
`created_after=Y-01-01T00:00:00Z` and `created_before=Y-12-31T23:59:59Z` so
GitLab filters the results. The service does not download everything and filter
locally.

**Pagination.** GitLab paginates list responses. The client requests
`per_page=100` and follows the `X-Next-Page` response header until it is empty,
concatenating every page.

**Two protocols, one core.** The HTTP API (`app/main.py`) and the MCP server
(`app/mcp_server.py`) are both thin adapters over the same reporting core
(`app/reports.py` + `app/gitlab_client.py`). The GitLab logic is written once
and reused, so the two entry points cannot drift apart.

## Local GitLab playground

To test against a self-hosted GitLab (matching GitLab 18.10 or newer), run the
official container. Pick the latest available `18.10+` tag at the time of
testing.

```bash
export GITLAB_HOME=/tmp/gitlab
sudo docker run --detach \
  --hostname gitlab.example.com \
  --env GITLAB_OMNIBUS_CONFIG="external_url 'http://gitlab.example.com'" \
  --publish 443:443 --publish 80:80 --publish 22:22 \
  --name gitlab \
  --restart always \
  --volume $GITLAB_HOME/config:/etc/gitlab \
  --volume $GITLAB_HOME/logs:/var/log/gitlab \
  --volume $GITLAB_HOME/data:/var/opt/gitlab \
  --shm-size 256m \
  gitlab/gitlab-ee:18.10.5-ee.0
```

GitLab needs a few minutes to boot. After it is up:

1. Create a group, a project, and a few issues and merge requests.
2. Create an access token with read permissions (`read_api` scope).
3. Point the service at it:

```bash
docker run --rm -p 8080:8080 \
  -e GITLAB_URL="http://gitlab.example.com" \
  -e GITLAB_TOKEN="<your-read-token>" \
  gitlab-yearly-report
```

Then run the curl commands above.
