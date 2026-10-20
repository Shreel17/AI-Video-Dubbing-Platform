from app.db.session import SessionLocal
from app.models.job import DubbingJob
from app.schemas.job import JobStatus
from main import run_dubbing_pipeline

def process_job(job_id: str) -> None:
    """Run the dubbing pipeline for a queued database job."""
    db = SessionLocal()
    
    try:
        # 1. Fetch and Validate Job
        job = db.get(DubbingJob, job_id)
        if job is None:
            print(f"Job {job_id} not found.")
            return
            
        if job.status != JobStatus.QUEUED:
            print(f"Job {job_id} is not queued. Current status: {job.status.value}")
            return

        # 2. Mark Job as Processing
        video_url = job.video_url
        job.status = JobStatus.PROCESSING
        job.progress = 1
        job.message = "Starting video dubbing."
        db.commit()

        # 3. Execute Pipeline outside database lock/transaction block
        try:
            output_path = run_dubbing_pipeline(
                video_url=video_url,
                job_id=job_id,
            )
        except Exception as exc:
            print(f"Dubbing failed for job {job_id}: {exc}")
            
            # Refresh session context state to avoid flush/commit conflicts
            db.rollback() 
            
            # Update to Failed Status
            job.status = JobStatus.FAILED
            job.message = f"Dubbing failed: {str(exc)[:400]}"
            db.commit()
            return

        # 4. Mark Job as Completed
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.message = "Dubbing completed successfully."
        job.output_path = str(output_path)
        db.commit()
        print(f"Dubbing completed for job {job_id}: {output_path}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
