# Author: Mathew — GitHub client tests using mocked HTTP responses.

import httpx
import pytest

from app.config import Settings
from app.github import GitHubAPIError, GitHubClient
from app.pagination import parse_link_header

SETTINGS = Settings(github_token="token", github_owner="owner", github_repo="repo")


def issue_data(number: int = 1) -> dict:
    return {
        "number": number,
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "state": "open",
        "title": "Example",
        "body": "Description",
        "labels": [{"name": "bug"}],
        "created_at": "2026-09-11T00:00:00Z",
        "updated_at": "2026-09-11T00:00:00Z",
    }


def client_for(handler) -> GitHubClient:
    return GitHubClient(SETTINGS, transport=httpx.MockTransport(handler), cache={})


@pytest.mark.asyncio
async def test_create_issue_sends_required_github_headers() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer token"
        assert request.headers["accept"] == "application/vnd.github+json"
        assert request.url.path == "/repos/owner/repo/issues"
        return httpx.Response(201, json=issue_data(), request=request)

    issue = await client_for(handler).create_issue({"title": "Example"})

    assert issue.labels[0].name == "bug"


@pytest.mark.asyncio
async def test_list_issues_filters_pull_requests_and_returns_link() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        pull_request = issue_data(2) | {"pull_request": {"url": "example"}}
        return httpx.Response(
            200,
            json=[issue_data(), pull_request],
            headers={"Link": '<https://api.github.com?page=2>; rel="next"'},
            request=request,
        )

    issues, link = await client_for(handler).list_issues({"state": "open", "page": 1, "per_page": 30})

    assert [issue.number for issue in issues] == [1]
    assert link is not None and 'rel="next"' in link


@pytest.mark.asyncio
@pytest.mark.parametrize("github_status", [401, 403, 404])
async def test_github_auth_and_not_found_errors_are_preserved(github_status: int) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(github_status, json={"message": "GitHub message"}, request=request)

    with pytest.raises(GitHubAPIError) as error:
        await client_for(handler).get_issue(1)

    assert error.value.status_code == github_status
    assert error.value.detail == "GitHub message"


@pytest.mark.asyncio
async def test_github_rate_limit_becomes_429() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0", "Retry-After": "60"},
            request=request,
        )

    with pytest.raises(GitHubAPIError) as error:
        await client_for(handler).get_issue(1)

    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_rate_limit_reset_is_converted_to_retry_after() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "4102444800"},
            request=request,
        )

    with pytest.raises(GitHubAPIError) as error:
        await client_for(handler).get_issue(1)

    assert int(error.value.headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_direct_github_429_is_preserved() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"message": "Too many requests"},
            headers={"Retry-After": "30"},
            request=request,
        )

    with pytest.raises(GitHubAPIError) as error:
        await client_for(handler).get_issue(1)

    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "30"


@pytest.mark.asyncio
async def test_github_server_error_becomes_503() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"message": "bad gateway"}, request=request)

    with pytest.raises(GitHubAPIError) as error:
        await client_for(handler).get_issue(1)

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_missing_github_configuration_returns_401() -> None:
    empty_settings = Settings(
        github_token="",
        github_owner="",
        github_repo="",
        _env_file=None,
    )
    with pytest.raises(GitHubAPIError) as error:
        await GitHubClient(empty_settings).get_issue(1)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_create_comment_maps_github_user() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "id": 5,
                "body": "Comment",
                "user": {"login": "octocat"},
                "created_at": "2026-09-11T00:00:00Z",
                "html_url": "https://github.com/owner/repo/issues/1#issuecomment-5",
            },
            request=request,
        )

    comment = await client_for(handler).create_comment(1, {"body": "Comment"})

    assert comment.user == "octocat"


@pytest.mark.asyncio
async def test_list_comments_maps_github_users() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": 5,
                    "body": "Comment",
                    "user": {"login": "octocat"},
                    "created_at": "2026-09-11T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/issues/1#issuecomment-5",
                }
            ],
            request=request,
        )

    comments = await client_for(handler).list_comments(1)

    assert comments[0].user == "octocat"


def test_parse_link_header_returns_pagination_relations() -> None:
    value = (
        '<https://api.github.com/repositories/1/issues?page=2>; rel="next", '
        '<https://api.github.com/repositories/1/issues?page=4>; rel="last"'
    )

    links = parse_link_header(value)

    assert links["next"].endswith("page=2")
    assert links["last"].endswith("page=4")


@pytest.mark.asyncio
async def test_list_issues_reuses_cached_etag() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json=[issue_data()],
                headers={"ETag": '"issue-list-v1"'},
                request=request,
            )
        assert request.headers["if-none-match"] == '"issue-list-v1"'
        return httpx.Response(304, request=request)

    client = client_for(handler)
    first, _ = await client.list_issues({"state": "open", "page": 1, "per_page": 30})
    second, _ = await client.list_issues({"state": "open", "page": 1, "per_page": 30})

    assert second == first
    assert calls == 2
