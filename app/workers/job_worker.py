
import re

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
    """Run the dubbing pipeline for a queued database job."""
    db = SessionLocal()

    try:
        job = db.get(DubbingJob, job_id)

        if job is None:
            print(f"Job {job_id} not found.")
            return

        if job.status != JobStatus.QUEUED:
            print(
                f"Job {job_id} is not queued. "
                f"Current status: {job.status.value}"
            )
            return

        video_url = job.video_url
        job.status = JobStatus.PROCESSING
        job.progress = 1
        job.message = "Starting video dubbing."
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    try:
        def save_progress(progress: int, message: str) -> None:
            """Save pipeline progress to the database."""
            progress_db = SessionLocal()

            try:
                progress_job = progress_db.get(
                    DubbingJob,
                    job_id,
                )

                if progress_job is not None:
                    # Reserve 100% for final job completion.
                    progress_job.progress = min(progress, 99)
                    progress_job.message = message
                    progress_db.commit()

            except Exception:
                progress_db.rollback()
                raise

            finally:
                progress_db.close()

        output_path = run_dubbing_pipeline(
            video_url=video_url,
            job_id=job_id,
            progress_callback=save_progress,
        )

    except Exception as exc:
        error_message = clean_error_message(exc)
        print(
            f"Dubbing failed for job {job_id}: "
            f"{error_message}"
        )

        failure_db = SessionLocal()

        try:
            failed_job = failure_db.get(
                DubbingJob,
                job_id,
            )

            if failed_job is not None:
                failed_job.status = JobStatus.FAILED
                failed_job.progress = 0
                failed_job.message = (
                    f"Dubbing failed: {error_message}"
                )
                failure_db.commit()

        except Exception:
            failure_db.rollback()
            raise

        finally:
            failure_db.close()

        return

    completion_db = SessionLocal()

    try:
        completed_job = completion_db.get(
            DubbingJob,
            job_id,
        )

        if completed_job is not None:
            completed_job.status = JobStatus.COMPLETED
            completed_job.progress = 100
            completed_job.message = (
                "Dubbing completed successfully."
            )
            completed_job.output_path = str(output_path)
            completion_db.commit()

        print(
            f"Dubbing completed for job {job_id}: "
            f"{output_path}"
        )

    except Exception:
        completion_db.rollback()
        raise

    finally:
        completion_db.close()
