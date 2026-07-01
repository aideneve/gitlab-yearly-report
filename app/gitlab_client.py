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
