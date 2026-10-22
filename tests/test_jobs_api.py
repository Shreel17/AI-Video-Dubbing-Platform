from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models.job import DubbingJob
from app.schemas.job import JobStatus


# Use a separate in-memory SQLite database for tests.
TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
)


def override_get_db():
    """Provide an isolated database session to API tests."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_create_and_retrieve_job():
    with patch("app.api.jobs.process_dubbing_job.delay") as mock_worker:
        response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=example",
                "target_language": "hi",
                "source_language": "en",
            },
        )

    assert response.status_code == 202

    created_job = response.json()
    assert created_job["status"] == "queued"
    assert created_job["progress"] == 0

    job_id = created_job["job_id"]
    mock_worker.assert_called_once_with(job_id)

    get_response = client.get(f"/api/v1/jobs/{job_id}")

    assert get_response.status_code == 200

    retrieved_job = get_response.json()
    assert retrieved_job["job_id"] == job_id
    assert retrieved_job["status"] == "queued"
    assert retrieved_job["progress"] == 0
    assert "output_path" in retrieved_job
    assert retrieved_job["output_path"] is None


def test_retrieve_job_returns_updated_progress():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=example",
                "target_language": "hi",
                "source_language": "en",
            },
        )

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    # Simulate progress updates saved by the background worker.
    with TestingSessionLocal() as db:
        job = db.get(DubbingJob, job_id)

        assert job is not None
        job.status = JobStatus.PROCESSING
        job.progress = 55
        job.message = "Translation completed. Preparing speech generation."
        db.commit()

    response = client.get(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 200

    job_data = response.json()
    assert job_data["job_id"] == job_id
    assert job_data["status"] == "processing"
    assert job_data["progress"] == 55
    assert job_data["message"] == (
        "Translation completed. Preparing speech generation."
    )
    assert job_data["output_path"] is None


def test_retrieve_nonexistent_job():
    response = client.get(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


def test_list_dubbing_jobs():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        first_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=first123",
                "target_language": "hi",
                "source_language": "en",
            },
        )
        second_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=second123",
                "target_language": "fr",
                "source_language": "en",
            },
        )

    assert first_response.status_code == 202
    assert second_response.status_code == 202

    first_id = first_response.json()["job_id"]
    second_id = second_response.json()["job_id"]

    response = client.get("/api/v1/jobs")

    assert response.status_code == 200

    jobs = response.json()
    returned_ids = [job["job_id"] for job in jobs]

    assert first_id in returned_ids
    assert second_id in returned_ids


def test_list_dubbing_jobs_pagination():
    response = client.get("/api/v1/jobs?limit=2&offset=0")

    assert response.status_code == 200
    assert len(response.json()) <= 2

    next_response = client.get("/api/v1/jobs?limit=2&offset=2")

    assert next_response.status_code == 200
    assert len(next_response.json()) <= 2


def test_list_dubbing_jobs_rejects_invalid_pagination():
    invalid_limit = client.get("/api/v1/jobs?limit=0")
    assert invalid_limit.status_code == 422

    invalid_offset = client.get("/api/v1/jobs?offset=-1")
    assert invalid_offset.status_code == 422


def test_list_dubbing_jobs_newest_first():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        older_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=older123",
                "target_language": "hi",
            },
        )
        newer_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=newer123",
                "target_language": "hi",
            },
        )

    assert older_response.status_code == 202
    assert newer_response.status_code == 202

    older_id = older_response.json()["job_id"]
    newer_id = newer_response.json()["job_id"]

    # Assign distinct timestamps to make ordering deterministic.
    with TestingSessionLocal() as db:
        older_job = db.get(DubbingJob, older_id)
        newer_job = db.get(DubbingJob, newer_id)

        assert older_job is not None
        assert newer_job is not None

        now = datetime.now(timezone.utc)
        older_job.created_at = now - timedelta(minutes=10)
        newer_job.created_at = now
        db.commit()

    response = client.get("/api/v1/jobs?limit=100&offset=0")

    assert response.status_code == 200

    returned_ids = [job["job_id"] for job in response.json()]

    assert returned_ids.index(newer_id) < returned_ids.index(older_id)


def test_list_dubbing_jobs_filters_by_status():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=filter123",
                "target_language": "hi",
            },
        )

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # Change this job's status to completed.
    with TestingSessionLocal() as db:
        job = db.get(DubbingJob, job_id)
        assert job is not None

        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.message = "Dubbing completed successfully."
        db.commit()

    response = client.get("/api/v1/jobs?status=completed")

    assert response.status_code == 200

    jobs = response.json()
    assert all(job["status"] == "completed" for job in jobs)
    assert any(job["job_id"] == job_id for job in jobs)


def test_list_dubbing_jobs_returns_only_requested_status():
    response = client.get("/api/v1/jobs?status=queued")

    assert response.status_code == 200
    assert all(
        job["status"] == "queued"
        for job in response.json()
    )


def test_list_dubbing_jobs_rejects_invalid_status():
    response = client.get("/api/v1/jobs?status=unknown")

    assert response.status_code == 422


def test_get_dubbing_job_stats():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=stats123",
                "target_language": "hi",
                "source_language": "en",
            },
        )

    assert response.status_code == 202

    response = client.get("/api/v1/jobs/stats")

    assert response.status_code == 200

    stats = response.json()

    assert stats["total_jobs"] >= 1
    assert stats["queued_jobs"] >= 0
    assert stats["processing_jobs"] >= 0
    assert stats["completed_jobs"] >= 0
    assert stats["failed_jobs"] >= 0
    assert stats["cancelled_jobs"] >= 0

    assert sum(
        stats[key]
        for key in [
            "queued_jobs",
            "processing_jobs",
            "completed_jobs",
            "failed_jobs",
            "cancelled_jobs",
        ]
    ) == stats["total_jobs"]


def test_retry_failed_job():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=retry123",
                "target_language": "hi",
                "source_language": "en",
            },
        )

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    # Simulate a previously failed job.
    with TestingSessionLocal() as db:
        job = db.get(DubbingJob, job_id)
        assert job is not None

        job.status = JobStatus.FAILED
        job.progress = 0
        job.message = "Dubbing failed: temporary error"
        job.completed_at = datetime.now(timezone.utc)
        job.processing_time_seconds = 10.0
        db.commit()

    with patch("app.api.jobs.process_dubbing_job.delay") as mock_worker:
        response = client.post(f"/api/v1/jobs/{job_id}/retry")

    assert response.status_code == 202

    data = response.json()
    assert data["job_id"] == job_id
    assert data["status"] == "queued"
    assert data["progress"] == 0
    assert data["message"] == (
        "Dubbing job retry accepted and queued for processing."
    )
    assert data["output_path"] is None
    assert data["completed_at"] is None
    assert data["processing_time_seconds"] is None

    mock_worker.assert_called_once_with(job_id)


def test_retry_non_failed_job_returns_conflict():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=noretry123",
                "target_language": "hi",
            },
        )

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    response = client.post(f"/api/v1/jobs/{job_id}/retry")

    assert response.status_code == 409
    assert response.json()["detail"] == "Only failed jobs can be retried"


def test_retry_nonexistent_job_returns_not_found():
    response = client.post(
        "/api/v1/jobs/"
        "00000000-0000-0000-0000-000000000000/retry"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dubbing job not found"


def test_retry_same_job_twice_rejects_second_request():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=retrytwice123",
                "target_language": "hi",
            },
        )

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    with TestingSessionLocal() as db:
        job = db.get(DubbingJob, job_id)
        assert job is not None
        job.status = JobStatus.FAILED
        job.message = "Dubbing failed: temporary error"
        db.commit()

    with patch("app.api.jobs.process_dubbing_job.delay") as mock_worker:
        first_response = client.post(
            f"/api/v1/jobs/{job_id}/retry"
        )
        second_response = client.post(
            f"/api/v1/jobs/{job_id}/retry"
        )

    assert first_response.status_code == 202
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Only failed jobs can be retried"
    )
    mock_worker.assert_called_once_with(job_id)


def test_download_completed_job():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=download123",
                "target_language": "hi",
            },
        )

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    with TemporaryDirectory() as temp_dir:
        video_path = Path(temp_dir) / "dubbed_video.mp4"
        video_path.write_bytes(b"fake mp4 test content")

        with TestingSessionLocal() as db:
            job = db.get(DubbingJob, job_id)
            assert job is not None
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.output_path = str(video_path)
            db.commit()

        response = client.get(
            f"/api/v1/jobs/{job_id}/download"
        )

        assert response.status_code == 200
        assert response.content == b"fake mp4 test content"
        assert "dubbed_video.mp4" in response.headers[
            "content-disposition"
        ]


def test_download_nonexistent_job_returns_not_found():
    response = client.get(
        "/api/v1/jobs/"
        "00000000-0000-0000-0000-000000000000/download"
    )

    assert response.status_code == 404


def test_download_incomplete_job_returns_conflict():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=incomplete123",
                "target_language": "hi",
            },
        )

    job_id = create_response.json()["job_id"]

    response = client.get(
        f"/api/v1/jobs/{job_id}/download"
    )

    assert response.status_code == 409


def test_download_missing_output_file_returns_not_found():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=missingfile123",
                "target_language": "hi",
            },
        )

    job_id = create_response.json()["job_id"]

    with TestingSessionLocal() as db:
        job = db.get(DubbingJob, job_id)
        assert job is not None
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.output_path = (
            "nonexistent_test_output_directory/dubbed_video.mp4"
        )
        db.commit()

    response = client.get(
        f"/api/v1/jobs/{job_id}/download"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Output video file not found"


def test_cancel_queued_job():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=cancel123",
                "target_language": "hi",
            },
        )

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    response = client.post(f"/api/v1/jobs/{job_id}/cancel")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["status"] == "cancelled"
    assert data["progress"] == 0
    assert data["message"] == (
        "Dubbing job cancelled before processing."
    )

    # Verify the status persisted in the database.
    with TestingSessionLocal() as db:
        job = db.get(DubbingJob, job_id)
        assert job is not None
        assert job.status == JobStatus.CANCELLED


def test_cancel_nonexistent_job_returns_not_found():
    response = client.post(
        "/api/v1/jobs/"
        "00000000-0000-0000-0000-000000000000/cancel"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dubbing job not found"


def test_cancel_processing_job_returns_conflict():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": (
                    "https://www.youtube.com/watch?v=cancelprocessing123"
                ),
                "target_language": "hi",
            },
        )

    job_id = create_response.json()["job_id"]

    with TestingSessionLocal() as db:
        job = db.get(DubbingJob, job_id)
        assert job is not None
        job.status = JobStatus.PROCESSING
        job.progress = 50
        db.commit()

    response = client.post(f"/api/v1/jobs/{job_id}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Only queued jobs can be cancelled"
    )


def test_cancel_same_job_twice_rejects_second_request():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": (
                    "https://www.youtube.com/watch?v=canceltwice123"
                ),
                "target_language": "hi",
            },
        )

    job_id = create_response.json()["job_id"]

    first_response = client.post(
        f"/api/v1/jobs/{job_id}/cancel"
    )
    second_response = client.post(
        f"/api/v1/jobs/{job_id}/cancel"
    )

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "cancelled"
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Only queued jobs can be cancelled"
    )


def teardown_module():
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_create_job_dispatch_failure_returns_503_and_preserves_job():
    with patch(
        "app.api.jobs.process_dubbing_job.delay",
        side_effect=RuntimeError("Celery unavailable"),
    ):
        response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=dispatchfail123",
                "target_language": "hi",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Job was saved, but the task could not be queued. "
        "Please check Redis and retry later."
    )

    with TestingSessionLocal() as db:
        jobs = (
            db.query(DubbingJob)
            .filter(
                DubbingJob.video_url
                == "https://www.youtube.com/watch?v=dispatchfail123"
            )
            .all()
        )

        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.QUEUED
        assert jobs[0].progress == 0


def test_retry_dispatch_failure_returns_503_and_preserves_queued_job():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=retrydispatchfail123",
                "target_language": "hi",
            },
        )

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    with TestingSessionLocal() as db:
        job = db.get(DubbingJob, job_id)
        assert job is not None
        job.status = JobStatus.FAILED
        job.progress = 80
        job.output_path = "old-output.mp4"
        job.completed_at = datetime.now(timezone.utc)
        job.processing_time_seconds = 12.5
        db.commit()

    with patch(
        "app.api.jobs.process_dubbing_job.delay",
        side_effect=RuntimeError("Celery unavailable"),
    ):
        response = client.post(f"/api/v1/jobs/{job_id}/retry")

    assert response.status_code == 503

    with TestingSessionLocal() as db:
        job = db.get(DubbingJob, job_id)
        assert job is not None
        assert job.status == JobStatus.QUEUED
        assert job.progress == 0
        assert job.output_path is None
        assert job.completed_at is None
        assert job.processing_time_seconds is None

def test_quality_report_returns_report_for_completed_job():
    import json

    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=quality123",
                "target_language": "hi",
            },
        )

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    expected_report = {
        "schema_version": 1,
        "overall_status": "passed",
        "checks": [],
        "warnings": [],
    }

    with TemporaryDirectory() as temp_dir:
        video_path = Path(temp_dir) / "dubbed_video.mp4"
        video_path.write_bytes(b"fake mp4 test content")

        report_path = video_path.parent / "quality_report.json"
        report_path.write_text(
            json.dumps(expected_report),
            encoding="utf-8",
        )

        with TestingSessionLocal() as db:
            job = db.get(DubbingJob, job_id)
            assert job is not None
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.output_path = str(video_path)
            db.commit()

        response = client.get(
            f"/api/v1/jobs/{job_id}/quality-report"
        )

        assert response.status_code == 200
        assert response.json() == expected_report


def test_quality_report_nonexistent_job_returns_not_found():
    response = client.get(
        "/api/v1/jobs/"
        "00000000-0000-0000-0000-000000000000/quality-report"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dubbing job not found"


def test_quality_report_incomplete_job_returns_conflict():
    with patch("app.api.jobs.process_dubbing_job.delay"):
        create_response = client.post(
            "/api/v1/jobs",
            json={
                "video_url": "https://www.youtube.com/watch?v=qualitypending",
                "target_language": "hi",
            },
        )

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    response = client.get(
        f"/api/v1/jobs/{job_id}/quality-report"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Quality report is available only for completed jobs"
    )
