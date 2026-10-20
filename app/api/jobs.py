from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import DubbingJob
from app.schemas.job import DubbingJobCreate, DubbingJobResponse, JobStatus
from app.workers.job_worker import process_job


router = APIRouter(prefix="/jobs", tags=["Dubbing Jobs"])


@router.post(
    "",
    response_model=DubbingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_dubbing_job(
    request: DubbingJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> DubbingJobResponse:
    job = DubbingJob(
        id=str(uuid4()),
        video_url=str(request.video_url),
        source_language=request.source_language,
        target_language=request.target_language,
        status=JobStatus.QUEUED,
        progress=0,
        message="Dubbing job accepted and queued for processing.",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    response = DubbingJobResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        output_path=job.output_path,
    )

    background_tasks.add_task(process_job, job.id)

    return response



@router.get("/{job_id}", response_model=DubbingJobResponse)
def get_dubbing_job(
    job_id: str,
    db: Session = Depends(get_db),
) -> DubbingJobResponse:
    job = db.get(DubbingJob, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dubbing job not found",
        )

    return DubbingJobResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        output_path=job.output_path,
    )
