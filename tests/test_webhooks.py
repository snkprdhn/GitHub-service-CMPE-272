# Author: Mathew — webhook signature, validation, and deduplication tests.

import hashlib
import hmac
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.webhooks import EventStore, WebhookService, get_event_store, get_webhook_service

SECRET = "test-webhook-secret"
STORE = EventStore()
ISSUE_FIXTURE = Path(__file__).parent / "fixtures" / "issue_opened.json"


def webhook_client() -> TestClient:
    service = WebhookService(Settings(webhook_secret=SECRET), STORE)
    app.dependency_overrides[get_webhook_service] = lambda: service
    app.dependency_overrides[get_event_store] = lambda: STORE
    return TestClient(app)


def signed_headers(body: bytes, event: str = "issues", delivery: str = "delivery-1") -> dict[str, str]:
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": f"sha256={signature}",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }


def teardown_function() -> None:
    STORE.clear()
    app.dependency_overrides.clear()


def test_valid_webhook_is_stored() -> None:
    body = ISSUE_FIXTURE.read_bytes()
    response = webhook_client().post("/webhook", content=body, headers=signed_headers(body))

    assert response.status_code == 204
    events = webhook_client().get("/events").json()
    assert events[0]["event"] == "issues"
    assert events[0]["issue_number"] == 7


def test_invalid_signature_is_rejected() -> None:
    body = b'{"action":"opened"}'
    headers = signed_headers(body)
    headers["X-Hub-Signature-256"] = "sha256=not-valid"

    assert webhook_client().post("/webhook", content=body, headers=headers).status_code == 401


def test_tampered_body_is_rejected() -> None:
    original = b'{"action":"opened"}'
    changed = b'{"action":"closed"}'

    response = webhook_client().post("/webhook", content=changed, headers=signed_headers(original))

    assert response.status_code == 401


def test_duplicate_delivery_is_recorded_once() -> None:
    body = json.dumps({"action": "opened", "issue": {"number": 8}}).encode()
    client = webhook_client()

    assert client.post("/webhook", content=body, headers=signed_headers(body)).status_code == 204
    assert client.post("/webhook", content=body, headers=signed_headers(body)).status_code == 204
    assert len(client.get("/events").json()) == 1


def test_unknown_event_is_rejected() -> None:
    body = b'{"action":"opened"}'

    response = webhook_client().post("/webhook", content=body, headers=signed_headers(body, event="push"))

    assert response.status_code == 400


def test_unknown_action_is_rejected() -> None:
    body = b'{"action":"unexpected"}'

    assert webhook_client().post("/webhook", content=body, headers=signed_headers(body)).status_code == 400


def test_issue_comment_event_is_stored() -> None:
    body = json.dumps({"action": "created", "issue": {"number": 9}}).encode()
    headers = signed_headers(body, event="issue_comment", delivery="comment-delivery")

    response = webhook_client().post("/webhook", content=body, headers=headers)

    assert response.status_code == 204
    assert webhook_client().get("/events").json()[0]["event"] == "issue_comment"


def test_ping_event_is_accepted() -> None:
    body = b'{"zen":"Keep it logically awesome."}'
    headers = signed_headers(body, event="ping", delivery="ping-delivery")

    response = webhook_client().post("/webhook", content=body, headers=headers)

    assert response.status_code == 204


def test_delivery_and_action_form_dedupe_key() -> None:
    opened = b'{"action":"opened","issue":{"number":10}}'
    closed = b'{"action":"closed","issue":{"number":10}}'
    client = webhook_client()

    assert client.post("/webhook", content=opened, headers=signed_headers(opened)).status_code == 204
    assert client.post("/webhook", content=closed, headers=signed_headers(closed)).status_code == 204
    assert len(client.get("/events").json()) == 2
