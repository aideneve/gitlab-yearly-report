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
