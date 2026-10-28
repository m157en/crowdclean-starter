from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class CreateUrlJob(BaseModel):
    source_url: HttpUrl


class AudioJobRead(BaseModel):
    id: str
    source_type: str
    source_url: str | None
    original_filename: str | None
    status: str
    duration_seconds: float | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AudioSegmentRead(BaseModel):
    id: int
    job_id: str
    start_seconds: float
    end_seconds: float
    label: str
    confidence: float
    decision: str

    model_config = ConfigDict(from_attributes=True)


class SegmentDecisionUpdate(BaseModel):
    decision: Literal["keep", "remove", "pending"]


class JobListRead(BaseModel):
    items: list[AudioJobRead]
    limit: int
    offset: int
    total: int
