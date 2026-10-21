import inspect
import re
import time
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.job import DubbingJob
from app.schemas.job import JobStatus
from main import run_dubbing_pipeline


def clean_error_message(error: Exception) -> str:
    """Remove terminal ANSI escape codes from an error message."""
    message = str(error)
    message = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", message)
    return message[:400]


def process_job(job_id: str) -> None:
    """Atomically claim and process a queued dubbing job."""
    db = SessionLocal()
    started_at = time.monotonic()

    try:
        updated_rows = (
            db.query(DubbingJob)
            .filter(
                DubbingJob.id == job_id,
                DubbingJob.status == JobStatus.QUEUED,
            )
            .update(
                {
                    DubbingJob.status: JobStatus.PROCESSING,
                    DubbingJob.progress: 1,
                    DubbingJob.message: "Starting video dubbing.",
                    DubbingJob.completed_at: None,
                    DubbingJob.processing_time_seconds: None,
                },
                synchronize_session=False,
            )
        )

        if updated_rows == 0:
            db.rollback()
            job = db.get(DubbingJob, job_id)

            if job is None:
                print(f"Job {job_id} not found.")
            else:
                print(
                    f"Job {job_id} was not started. "
                    f"Current status: {job.status.value}"
                )
            return

        db.commit()
        job = db.get(DubbingJob, job_id)

        if job is None:
            print(f"Job {job_id} not found after claiming.")
            return

        video_url = job.video_url
        target_language = job.target_language

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    def elapsed_seconds() -> float:
        return round(time.monotonic() - started_at, 2)

    def save_progress(progress: int, message: str) -> None:
        """Save progress only while the job is processing."""
        progress_db = SessionLocal()

        try:
            progress_job = progress_db.get(DubbingJob, job_id)

            if (
                progress_job is not None
                and progress_job.status == JobStatus.PROCESSING
            ):
                progress_job.progress = min(max(progress, 1), 99)
                progress_job.message = message
                progress_db.commit()

        except Exception:
            progress_db.rollback()
            raise

        finally:
            progress_db.close()

    try:
        # Preserve compatibility with test doubles and older callables.
        # The real pipeline accepts target_language, so Hindi dubbing
        # remains enabled in normal operation.
        parameters = inspect.signature(
            run_dubbing_pipeline
        ).parameters

        pipeline_kwargs = {
            "video_url": video_url,
            "job_id": job_id,
            "progress_callback": save_progress,
        }

        if (
            "target_language" in parameters
            or any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
        ):
            pipeline_kwargs["target_language"] = target_language

        output_path = run_dubbing_pipeline(**pipeline_kwargs)

    except Exception as exc:
        error_message = clean_error_message(exc)
        print(f"Dubbing failed for job {job_id}: {error_message}")

        failure_db = SessionLocal()

        try:
            failed_job = failure_db.get(DubbingJob, job_id)

            if (
                failed_job is not None
                and failed_job.status == JobStatus.PROCESSING
            ):
                failed_job.status = JobStatus.FAILED
                failed_job.progress = 0
                failed_job.message = f"Dubbing failed: {error_message}"
                failed_job.completed_at = datetime.now(timezone.utc)
                failed_job.processing_time_seconds = elapsed_seconds()
                failure_db.commit()

        except Exception:
            failure_db.rollback()
            raise

        finally:
            failure_db.close()

        return

    completion_db = SessionLocal()

    try:
        completed_job = completion_db.get(DubbingJob, job_id)

        if (
            completed_job is not None
            and completed_job.status == JobStatus.PROCESSING
        ):
            completed_job.status = JobStatus.COMPLETED
            completed_job.progress = 100
            completed_job.message = "Dubbing completed successfully."
            completed_job.output_path = str(output_path)
            completed_job.completed_at = datetime.now(timezone.utc)
            completed_job.processing_time_seconds = elapsed_seconds()
            completion_db.commit()

            print(
                f"Dubbing completed for job {job_id}: {output_path}"
            )

    except Exception:
        completion_db.rollback()
        raise

    finally:
        completion_db.close()