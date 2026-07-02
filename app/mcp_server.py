import logging

from mcp.server.fastmcp import FastMCP

from . import reports
from .config import load_settings
from .gitlab_client import GitLabClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = load_settings()
gitlab_client = GitLabClient(
    settings.gitlab_url, settings.gitlab_token, settings.request_timeout
)

mcp = FastMCP("gitlab-yearly-report")


@mcp.tool()
def get_issues_by_year(year: int, project: str | None = None) -> dict:
    """Return GitLab issues created during the given year.

    Args:
        year: 4-digit year, for example 2025.
        project: Optional GitLab project ID or path (e.g. "mygroup/my-project").
            If omitted, reports across the entire instance the token can see.
    """
    return reports.get_issues_by_year(gitlab_client, year, project)


@mcp.tool()
def get_merge_requests_by_year(year: int, project: str | None = None) -> dict:
    """Return GitLab merge requests created during the given year.

    Args:
        year: 4-digit year, for example 2025.
        project: Optional GitLab project ID or path (e.g. "mygroup/my-project").
            If omitted, reports across the entire instance the token can see.
    """
    return reports.get_merge_requests_by_year(gitlab_client, year, project)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
