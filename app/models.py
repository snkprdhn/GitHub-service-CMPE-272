"""Request and response models for the public API."""

# Author: Sonit — API request and response model definitions.

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Label(BaseModel):
    name: str


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    body: str | None = None
    labels: list[str] = Field(default_factory=list)


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    body: str | None = None
    state: Literal["open", "closed"] | None = None


class Issue(BaseModel):
    number: int
    html_url: str
    state: str
    title: str
    body: str | None = None
    labels: list[Label] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


class Comment(BaseModel):
    id: int
    body: str
    user: str
    created_at: datetime
    html_url: str


class ErrorResponse(BaseModel):
    detail: str
    status: int
    request_id: str | None = None


class EventRecord(BaseModel):
    id: str
    event: str
    action: str | None = None
    issue_number: int | None = None
    timestamp: datetime
