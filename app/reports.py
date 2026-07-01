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
