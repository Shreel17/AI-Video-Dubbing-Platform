import pytest
from pydantic import ValidationError

from app.schemas.job import (
    DubbingJobCreate,
    DubbingJobResponse,
    JobStatus,
)


def test_valid_dubbing_job_request():
    job = DubbingJobCreate(
        video_url="https://www.youtube.com/watch?v=example",
        target_language="en",
    )

    assert str(job.video_url).startswith("https://")
    assert job.target_language == "en"
    assert job.source_language is None


def test_default_target_language():
    job = DubbingJobCreate(
        video_url="https://example.com/video",
    )

    assert job.target_language == "en"


def test_invalid_url_is_rejected():
    with pytest.raises(ValidationError):
        DubbingJobCreate(video_url="not-a-valid-url")


def test_job_response():
    response = DubbingJobResponse(
        job_id="test-123",
        status=JobStatus.QUEUED,
        progress=0,
        message="Job created",
    )

    assert response.status == JobStatus.QUEUED
    assert response.progress == 0
