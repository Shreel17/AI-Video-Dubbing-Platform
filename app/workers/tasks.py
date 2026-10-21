from app.workers.celery_app import celery_app
from app.workers.job_worker import process_job

@celery_app.task(name="app.workers.tasks.process_dubbing_job")
def process_dubbing_job(job_id: str) -> None:
    """Run an existing dubbing job through the Celery worker."""
    process_job(job_id)