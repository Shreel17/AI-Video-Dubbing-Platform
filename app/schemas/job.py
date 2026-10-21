
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DubbingJobCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    video_url: HttpUrl
    target_language: str = Field(
        default="en",
        min_length=2,
        max_length=10,
        description="Target language code, such as en or hi",
    )
    source_language: str | None = Field(
        default=None,
        min_length=2,
        max_length=10,
        description="Optional source language code, or auto-detect",
    )


class DubbingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    message: str
    output_path: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    processing_time_seconds: float | None = None
