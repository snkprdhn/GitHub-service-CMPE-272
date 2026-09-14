"""Webhook signature verification and short-lived delivery storage."""

# Author: Joel — webhook HMAC validation, event processing, and idempotency store.

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.models import EventRecord

logger = logging.getLogger("github_issues_service.webhooks")
SUPPORTED_ACTIONS = {
    "issues": {
        "opened", "edited", "deleted", "transferred", "pinned", "unpinned", "closed", "reopened",
        "assigned", "unassigned", "labeled", "unlabeled", "locked", "unlocked", "milestoned", "demilestoned",
    },
    "issue_comment": {"created", "edited", "deleted"},
}


class WebhookError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class EventStore:
    """In-memory delivery store using delivery ID and action as the dedupe key."""

    def __init__(self) -> None:
        self._deliveries: set[tuple[str, str | None]] = set()
        self._events: list[EventRecord] = []

    def add(self, record: EventRecord) -> bool:
        key = (record.id, record.action)
        if key in self._deliveries:
            return False
        self._deliveries.add(key)
        self._events.insert(0, record)
        return True

    def recent(self, limit: int) -> list[EventRecord]:
        return self._events[:limit]

    def clear(self) -> None:
        self._deliveries.clear()
        self._events.clear()


class WebhookService:
    def __init__(self, settings: Settings, store: EventStore):
        self.settings = settings
        self.store = store

    def process(
        self,
        body: bytes,
        signature: str | None,
        event: str | None,
        delivery_id: str | None,
        request_id: str,
    ) -> None:
        self._verify_signature(body, signature)
        if event not in {"ping", "issues", "issue_comment"}:
            raise WebhookError(400, "Unsupported GitHub event")
        if not delivery_id:
            raise WebhookError(400, "Missing GitHub delivery ID")

        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, ValueError) as exc:
            raise WebhookError(400, "Invalid JSON payload") from exc

        action = payload.get("action")
        if event != "ping" and not action:
            raise WebhookError(400, "Webhook action is missing")
        if event != "ping" and action not in SUPPORTED_ACTIONS[event]:
            raise WebhookError(400, "Unsupported webhook action")
        issue = payload.get("issue") or {}
        stored = self.store.add(
            EventRecord(
                id=delivery_id,
                event=event,
                action=action,
                issue_number=issue.get("number"),
                timestamp=datetime.now(timezone.utc),
            )
        )
        logger.info(
            json.dumps(
                {
                    "message": "webhook_processed",
                    "request_id": request_id,
                    "delivery_id": delivery_id,
                    "event": event,
                    "action": action,
                    "issue_number": issue.get("number"),
                    "duplicate": not stored,
                }
            )
        )

    def _verify_signature(self, body: bytes, signature: str | None) -> None:
        if not self.settings.webhook_secret or not signature:
            raise WebhookError(401, "Webhook signature is invalid")
        expected = "sha256=" + hmac.new(
            self.settings.webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise WebhookError(401, "Webhook signature is invalid")


event_store = EventStore()


def get_event_store() -> EventStore:
    return event_store


def get_webhook_service() -> WebhookService:
    return WebhookService(get_settings(), event_store)
