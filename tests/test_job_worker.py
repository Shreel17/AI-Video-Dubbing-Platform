from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.job import DubbingJob
from app.schemas.job import JobStatus
from app.workers import job_worker


def create_test_database(monkeypatch):
    """Create an isolated in-memory database for worker tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(
        job_worker,
        "SessionLocal",
        TestingSessionLocal,
    )

    return engine, TestingSessionLocal


def create_job(TestingSessionLocal, status=JobStatus.QUEUED):
    """Insert a dubbing job and return its ID."""
    job_id = str(uuid4())

    with TestingSessionLocal() as db:
        db.add(
            DubbingJob(
                id=job_id,
                video_url="https://www.youtube.com/watch?v=example",
                source_language="en",
                target_language="hi",
                status=status,
                progress=(
                    0 if status == JobStatus.QUEUED else 100
                ),
                message="Job created",
            )
        )
        db.commit()

    return job_id


def test_worker_marks_job_completed_and_saves_output(
    monkeypatch,
    tmp_path,
):
    engine, TestingSessionLocal = create_test_database(monkeypatch)

    try:
        job_id = create_job(TestingSessionLocal)
        output_file = tmp_path / "dubbed_video.mp4"

        expected_job_id = job_id

        def fake_pipeline(video_url: str, job_id: str) -> Path:
            assert video_url == (
                "https://www.youtube.com/watch?v=example"
            )
            assert job_id == expected_job_id
            return output_file

        monkeypatch.setattr(
            job_worker,
            "run_dubbing_pipeline",
            fake_pipeline,
        )

        job_worker.process_job(job_id)

        with TestingSessionLocal() as db:
            job = db.get(DubbingJob, job_id)

            assert job is not None
            assert job.status == JobStatus.COMPLETED
            assert job.progress == 100
            assert job.output_path == str(output_file)
            assert job.message == "Dubbing completed successfully."

    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_worker_marks_job_failed_when_pipeline_raises(monkeypatch):
    engine, TestingSessionLocal = create_test_database(monkeypatch)

    try:
        job_id = create_job(TestingSessionLocal)

        def failing_pipeline(video_url: str, job_id: str) -> Path:
            raise RuntimeError("Simulated dubbing failure")

        monkeypatch.setattr(
            job_worker,
            "run_dubbing_pipeline",
            failing_pipeline,
        )

        job_worker.process_job(job_id)

        with TestingSessionLocal() as db:
            job = db.get(DubbingJob, job_id)

            assert job is not None
            assert job.status == JobStatus.FAILED
            assert job.progress == 0
            assert job.message == (
                "Dubbing failed: Simulated dubbing failure"
            )

    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_worker_skips_completed_job(monkeypatch):
    engine, TestingSessionLocal = create_test_database(monkeypatch)

    try:
        job_id = create_job(
            TestingSessionLocal,
            status=JobStatus.COMPLETED,
        )

        def unexpected_pipeline(video_url: str, job_id: str) -> Path:
            raise AssertionError(
                "Pipeline must not run for a completed job"
            )

        monkeypatch.setattr(
            job_worker,
            "run_dubbing_pipeline",
            unexpected_pipeline,
        )

        job_worker.process_job(job_id)

        with TestingSessionLocal() as db:
            job = db.get(DubbingJob, job_id)

            assert job is not None
            assert job.status == JobStatus.COMPLETED

    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_worker_skips_nonexistent_job(monkeypatch):
    engine, TestingSessionLocal = create_test_database(monkeypatch)

    try:
        def unexpected_pipeline(video_url: str, job_id: str) -> Path:
            raise AssertionError(
                "Pipeline must not run for a nonexistent job"
            )

        monkeypatch.setattr(
            job_worker,
            "run_dubbing_pipeline",
            unexpected_pipeline,
        )

        job_worker.process_job(str(uuid4()))

    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_clean_error_message_removes_ansi_codes():
    error = "\x1b[0;31mERROR:\x1b[0m Download failed"

    result = job_worker.clean_error_message(
        Exception(error)
    )

    assert result == "ERROR: Download failed"
