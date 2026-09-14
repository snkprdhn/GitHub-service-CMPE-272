"""Routes for receiving and viewing GitHub webhook deliveries."""

# Author: Joel — webhook receipt and event inspection routes.

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.models import EventRecord
from app.webhooks import EventStore, WebhookService, get_event_store, get_webhook_service

router = APIRouter(tags=["webhooks"])
Service = Annotated[WebhookService, Depends(get_webhook_service)]
Store = Annotated[EventStore, Depends(get_event_store)]


@router.post("/webhook", status_code=204)
async def receive_webhook(request: Request, service: Service) -> Response:
    body = await request.body()
    service.process(
        body=body,
        signature=request.headers.get("X-Hub-Signature-256"),
        event=request.headers.get("X-GitHub-Event"),
        delivery_id=request.headers.get("X-GitHub-Delivery"),
        request_id=request.state.request_id,
    )
    return Response(status_code=204)


@router.get("/events", response_model=list[EventRecord])
async def list_events(store: Store, limit: int = Query(default=20, ge=1, le=100)) -> list[EventRecord]:
    return store.recent(limit)
