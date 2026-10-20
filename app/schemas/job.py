from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


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
    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    message: str
    output_path:str | None = None