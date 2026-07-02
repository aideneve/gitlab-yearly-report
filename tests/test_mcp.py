import asyncio

from app import mcp_server


class FakeClient:
    def __init__(self, items):
        self._items = items

    def get_all(self, path, params=None):
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
    }
]


def test_both_tools_registered():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"get_issues_by_year", "get_merge_requests_by_year"}


def test_issues_tool_returns_report(monkeypatch):
    monkeypatch.setattr(mcp_server, "gitlab_client", FakeClient(RAW))
    result = mcp_server.get_issues_by_year(2025)
    assert result["year"] == 2025
    assert result["scope"] == "instance"
    assert result["count"] == 1
    assert result["items"][0]["author"] == "jdoe"


def test_merge_requests_tool_returns_report(monkeypatch):
    monkeypatch.setattr(mcp_server, "gitlab_client", FakeClient(RAW))
    result = mcp_server.get_merge_requests_by_year(2025, "mygroup/my-project")
    assert result["scope"] == "project:mygroup/my-project"
    assert result["count"] == 1
