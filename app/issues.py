"""Issue and comment routes."""

# Author: Sagar — issue and comment route handlers.

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.github import GitHubClient, get_github_client
from app.models import Comment, CommentCreate, Issue, IssueCreate, IssueUpdate

router = APIRouter(tags=["issues"])
Client = Annotated[GitHubClient, Depends(get_github_client)]


@router.post("/issues", response_model=Issue, status_code=201)
async def create_issue(payload: IssueCreate, response: Response, client: Client) -> Issue:
    issue = await client.create_issue(payload.model_dump())
    response.headers["Location"] = f"/issues/{issue.number}"
    return issue


@router.get("/issues", response_model=list[Issue])
async def list_issues(
    response: Response,
    client: Client,
    state: Literal["open", "closed", "all"] = "open",
    labels: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
) -> list[Issue]:
    params: dict[str, str | int] = {"state": state, "page": page, "per_page": per_page}
    if labels:
        params["labels"] = labels
    issues, link = await client.list_issues(params)
    if link:
        response.headers["Link"] = link
    return issues


@router.get("/issues/{number}", response_model=Issue)
async def get_issue(number: int, client: Client) -> Issue:
    return await client.get_issue(number)


@router.patch("/issues/{number}", response_model=Issue)
async def update_issue(number: int, payload: IssueUpdate, client: Client) -> Issue:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        from app.github import GitHubAPIError

        raise GitHubAPIError(400, "At least one field must be provided")
    return await client.update_issue(number, values)


@router.post("/issues/{number}/comments", response_model=Comment, status_code=201)
async def create_comment(number: int, payload: CommentCreate, client: Client) -> Comment:
    return await client.create_comment(number, payload.model_dump())
