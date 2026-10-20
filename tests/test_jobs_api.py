
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models.job import DubbingJob
from app.workers import job_worker
from unittest.mock import patch

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
    assert get_response.json()["job_id"] == job_id
    assert get_response.json()["status"] == "queued"
    assert "output_path" in get_response.json()
    assert get_response.json()["output_path"] is None

def test_retrieve_nonexistent_job():
    response = client.get(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


def teardown_module():
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
