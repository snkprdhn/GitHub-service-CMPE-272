"""Optional live tests against the configured GitHub repository and running service."""

# Author: Mathew — live GitHub issue and comment lifecycle test.

import asyncio

import httpx
import pytest

from app.config import Settings
from app.github import GitHubClient
from app.main import app

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_issue_lifecycle_against_github() -> None:
    settings = Settings()
    if not all((settings.github_token, settings.github_owner, settings.github_repo)):
        pytest.skip("Live GitHub credentials are not configured")

    github = GitHubClient(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://service") as service:
        created_response = await service.post(
            "/issues",
            json={"title": "integration test issue", "body": "Created by pytest."},
        )
        assert created_response.status_code == 201
        assert created_response.headers["Location"].startswith("/issues/")
        issue_number = created_response.json()["number"]

        fetched = await service.get(f"/issues/{issue_number}")
        assert fetched.status_code == 200

        updated = await service.patch(
            f"/issues/{issue_number}",
            json={"title": "integration test updated", "body": "Updated by pytest.", "state": "closed"},
        )
        assert updated.status_code == 200
        assert updated.json()["state"] == "closed"

        reopened = await service.patch(f"/issues/{issue_number}", json={"state": "open"})
        assert reopened.status_code == 200
        assert reopened.json()["state"] == "open"

        comment_response = await service.post(
            f"/issues/{issue_number}/comments",
            json={"body": "integration test comment"},
        )
        assert comment_response.status_code == 201
        comment_id = comment_response.json()["id"]

        comments = await github.list_comments(issue_number)
        assert any(saved.id == comment_id for saved in comments)

        await service.patch(f"/issues/{issue_number}", json={"state": "closed"})


@pytest.mark.asyncio
async def test_real_webhook_is_exposed_by_events_endpoint() -> None:
    settings = Settings()
    service_url = settings.service_base_url
    if not service_url or not all((settings.github_token, settings.github_owner, settings.github_repo)):
        pytest.skip("Running service, tunnel, webhook, and GitHub credentials are required")

    async with httpx.AsyncClient(base_url=service_url, timeout=10.0) as service:
        created = await service.post(
            "/issues",
            json={"title": "webhook integration test", "body": "Wait for the GitHub delivery."},
        )
        assert created.status_code == 201
        issue_number = created.json()["number"]

        found = False
        for _ in range(20):
            events = await service.get("/events?limit=100")
            assert events.status_code == 200
            found = any(
                item["event"] == "issues"
                and item["action"] == "opened"
                and item["issue_number"] == issue_number
                for item in events.json()
            )
            if found:
                break
            await asyncio.sleep(1)

        await service.patch(f"/issues/{issue_number}", json={"state": "closed"})
        assert found, "GitHub webhook delivery did not appear in /events within 20 seconds"
