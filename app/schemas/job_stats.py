from pydantic import BaseModel, Field


class DubbingJobStats(BaseModel):
    total_jobs: int = Field(ge=0)
    queued_jobs: int = Field(ge=0)
    processing_jobs: int = Field(ge=0)
    completed_jobs: int = Field(ge=0)
    failed_jobs: int = Field(ge=0)
    cancelled_jobs: int = Field(ge=0)
