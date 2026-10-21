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
    with patch("app.api.jobs.process_job") as mock_worker:
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
    with patch("app.api.jobs.process_job"):
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


def teardown_module():
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
