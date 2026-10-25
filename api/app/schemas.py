"""Pydantic schemas for the notebooks - the http contract."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

NotebookName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
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
