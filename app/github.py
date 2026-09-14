"""Minimal GitHub REST API client used by the route handlers."""

# Author: Sagar — GitHub REST client, pagination, and upstream error mapping.

from dataclasses import dataclass
from time import time
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.models import Comment, Issue, Label
from app.pagination import parse_link_header

GITHUB_API_URL = "https://api.github.com"


@dataclass
class GitHubResult:
    data: Any
    headers: dict[str, str]
    status_code: int


class GitHubAPIError(Exception):
    def __init__(self, status_code: int, detail: str, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}
        super().__init__(detail)


class GitHubClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        cache: dict[str, tuple[str, list[Issue], str | None]] | None = None,
    ):
        self.settings = settings
        self.transport = transport
        self.cache = cache if cache is not None else issue_cache

    @property
    def repository_url(self) -> str:
        return f"{GITHUB_API_URL}/repos/{self.settings.github_owner}/{self.settings.github_repo}"

    def _ensure_configured(self) -> None:
        if not all((self.settings.github_token, self.settings.github_owner, self.settings.github_repo)):
            raise GitHubAPIError(401, "GitHub credentials or repository configuration are missing")

    async def _request(self, method: str, path: str, **kwargs: Any) -> GitHubResult:
        self._ensure_configured()
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.settings.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        request_headers = headers | kwargs.pop("headers", {})
        async with httpx.AsyncClient(transport=self.transport, timeout=10.0) as client:
            try:
                response = await client.request(
                    method,
                    f"{self.repository_url}{path}",
                    headers=request_headers,
                    **kwargs,
                )
            except httpx.RequestError as exc:
                raise GitHubAPIError(503, "GitHub is temporarily unavailable") from exc

        if response.is_error:
            raise self._to_error(response)

        return GitHubResult(
            data=response.json() if response.content else None,
            headers=dict(response.headers),
            status_code=response.status_code,
        )

    @staticmethod
    def _to_error(response: httpx.Response) -> GitHubAPIError:
        try:
            message = response.json().get("message", "GitHub request failed")
        except ValueError:
            message = "GitHub request failed"

        headers: dict[str, str] = {}
        if response.headers.get("retry-after"):
            headers["Retry-After"] = response.headers["retry-after"]
        elif response.headers.get("x-ratelimit-reset"):
            reset_at = int(response.headers["x-ratelimit-reset"])
            headers["Retry-After"] = str(max(1, reset_at - int(time())))

        rate_limited = response.status_code == 429 or (
            response.status_code == 403
            and (
                response.headers.get("x-ratelimit-remaining") == "0"
                or "Retry-After" in headers
            )
        )
        if rate_limited:
            return GitHubAPIError(429, "GitHub rate limit exceeded", headers)
        if response.status_code in (401, 403, 404):
            return GitHubAPIError(response.status_code, message, headers)
        if response.status_code >= 500:
            return GitHubAPIError(503, "GitHub is temporarily unavailable", headers)
        return GitHubAPIError(400, message, headers)

    async def create_issue(self, payload: dict[str, Any]) -> Issue:
        result = await self._request("POST", "/issues", json=payload)
        return issue_from_github(result.data)

    async def list_issues(self, params: dict[str, Any]) -> tuple[list[Issue], str | None]:
        cache_key = "&".join(f"{key}={params[key]}" for key in sorted(params))
        cached = self.cache.get(cache_key)
        conditional_headers = {"If-None-Match": cached[0]} if cached else {}
        result = await self._request("GET", "/issues", params=params, headers=conditional_headers)
        if result.status_code == 304 and cached:
            return cached[1], cached[2]

        issues = [issue_from_github(item) for item in result.data if "pull_request" not in item]
        link = result.headers.get("link")
        parse_link_header(link)
        if result.headers.get("etag"):
            self.cache[cache_key] = (result.headers["etag"], issues, link)
        return issues, link

    async def get_issue(self, number: int) -> Issue:
        result = await self._request("GET", f"/issues/{number}")
        return issue_from_github(result.data)

    async def update_issue(self, number: int, payload: dict[str, Any]) -> Issue:
        result = await self._request("PATCH", f"/issues/{number}", json=payload)
        return issue_from_github(result.data)

    async def create_comment(self, number: int, payload: dict[str, Any]) -> Comment:
        result = await self._request("POST", f"/issues/{number}/comments", json=payload)
        return comment_from_github(result.data)

    async def list_comments(self, number: int) -> list[Comment]:
        result = await self._request("GET", f"/issues/{number}/comments")
        return [comment_from_github(comment) for comment in result.data]


def issue_from_github(data: dict[str, Any]) -> Issue:
    return Issue(
        number=data["number"],
        html_url=data["html_url"],
        state=data["state"],
        title=data["title"],
        body=data.get("body"),
        labels=[Label(name=label["name"]) for label in data.get("labels", [])],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def comment_from_github(data: dict[str, Any]) -> Comment:
    return Comment(
        id=data["id"],
        body=data["body"],
        user=data["user"]["login"],
        created_at=data["created_at"],
        html_url=data["html_url"],
    )


def get_github_client() -> GitHubClient:
    return GitHubClient(get_settings())


issue_cache: dict[str, tuple[str, list[Issue], str | None]] = {}
