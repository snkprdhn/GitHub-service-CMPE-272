# Author: Mathew — issue and comment route tests.

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.github import get_github_client
from app.main import app
from app.models import Comment, Issue

NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)
ISSUE = Issue(
    number=12,
    html_url="https://github.com/example/repo/issues/12",
    state="open",
    title="Test issue",
    body="Body",
    created_at=NOW,
    updated_at=NOW,
)


class FakeGitHubClient:
    async def create_issue(self, payload):
        assert payload["title"] == "Test issue"
        return ISSUE

    async def list_issues(self, params):
        assert params["state"] == "open"
        return [ISSUE], '<https://api.github.com/page=2>; rel="next"'

    async def get_issue(self, number):
        assert number == 12
        return ISSUE

    async def update_issue(self, number, payload):
        assert number == 12
        return ISSUE.model_copy(update={"state": payload.get("state", "open")})

    async def create_comment(self, number, payload):
        return Comment(
            id=4,
            body=payload["body"],
            user="octocat",
            created_at=NOW,
            html_url="https://github.com/example/repo/issues/12#issuecomment-4",
        )


def client() -> TestClient:
    app.dependency_overrides[get_github_client] = FakeGitHubClient
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_create_issue_sets_location_header() -> None:
    response = client().post("/issues", json={"title": "Test issue"})

    assert response.status_code == 201
    assert response.headers["location"] == "/issues/12"
    assert response.json()["number"] == 12


def test_missing_title_returns_bad_request() -> None:
    response = client().post("/issues", json={})

    assert response.status_code == 400


def test_list_issues_forwards_link_header() -> None:
    response = client().get("/issues?state=open&per_page=30")

    assert response.status_code == 200
    assert response.headers["link"].endswith('rel="next"')


def test_invalid_state_returns_bad_request() -> None:
    response = client().get("/issues?state=invalid")

    assert response.status_code == 400


def test_update_requires_at_least_one_field() -> None:
    response = client().patch("/issues/12", json={})

    assert response.status_code == 400


def test_create_comment() -> None:
    response = client().post("/issues/12/comments", json={"body": "Looks good"})

    assert response.status_code == 201
    assert response.json()["user"] == "octocat"
