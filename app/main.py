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
    return JSONResponse(
        status_code=400, content={"detail": "Invalid or missing query parameters"}
    )


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
