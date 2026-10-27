"""Pydantic schemas for the API - the HTTP contract."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, HttpUrl, StringConstraints, field_validator

NotebookName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]

SourceKind = Literal["pdf", "text", "url", "youtube", "vtt"]
SourceStatus = Literal["queued", "processing", "ready", "failed"]
SourceStage = Literal["extracting", "chunking", "embedding", "indexing"]

SourceTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=200),
]
SourceText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class NotebookCreate(BaseModel):
    """Body for POST /notebooks"""

    name: NotebookName


class NotebookUpdate(BaseModel):
    """Body for PATCH /notebooks/{notebook_id} - only the name for now."""

    name: NotebookName


class NotebookRead(BaseModel):
    """Notebook as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class SourceCreate(BaseModel):
    """Multipart form fields for POST /notebooks/{id}/sources.

    P2.1 accepts text only; each later source kind widens the literal and
    adds its own payload fields.
    """

    kind: Literal["text"]
    title: SourceTitle | None = None
    text: SourceText

    @field_validator("title")
    @classmethod
    def _blank_title_to_none(cls, value: str | None) -> str | None:
        return value or None


class SourceUrlCreate(BaseModel):
    """Multipart form fields for a website source."""

    kind: Literal["url"]
    title: SourceTitle | None = None
    url: HttpUrl

    @field_validator("title")
    @classmethod
    def _blank_title_to_none(cls, value: str | None) -> str | None:
        return value or None


class SourceYoutubeCreate(BaseModel):
    """Multipart form fields for a YouTube source."""

    kind: Literal["youtube"]
    title: SourceTitle | None = None
    url: HttpUrl

    @field_validator("title")
    @classmethod
    def _blank_title_to_none(cls, value: str | None) -> str | None:
        return value or None


class SourceContentRead(BaseModel):
    """Stored text snapshot, used by the web viewer."""

    model_config = ConfigDict(from_attributes=True)

    text: str | None
    pages: list[dict[str, Any]] | None
    segments: list[dict[str, Any]] | None


class SourceRead(BaseModel):
    """Source as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notebook_id: uuid.UUID
    kind: SourceKind
    title: str
    status: SourceStatus
    stage: SourceStage | None
    error: str | None
    chunk_count: int | None
    char_count: int | None
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
