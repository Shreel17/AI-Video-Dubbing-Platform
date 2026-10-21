from uuid import uuid4
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import DubbingJob
from app.schemas.job import (
    DubbingJobCreate,
    DubbingJobResponse,
    JobStatus,
)
from app.schemas.job_stats import DubbingJobStats
from app.workers.tasks import process_dubbing_job


router = APIRouter(prefix="/jobs", tags=["Dubbing Jobs"])


def build_job_response(job: DubbingJob) -> DubbingJobResponse:
    """Convert a database job into the public API response."""
    return DubbingJobResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        output_path=job.output_path,
        created_at=job.created_at,
        completed_at=job.completed_at,
        processing_time_seconds=job.processing_time_seconds,
    )


@router.get("", response_model=list[DubbingJobResponse])
def list_dubbing_jobs(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    job_status: JobStatus | None = Query(
        default=None,
        alias="status",
        description=(
            "Filter jobs by status: queued, processing, completed, "
            "failed, or cancelled"
        ),
    ),
    db: Session = Depends(get_db),
) -> list[DubbingJobResponse]:
    """List dubbing jobs with optional status filtering and pagination."""
    query = db.query(DubbingJob)

    if job_status is not None:
        query = query.filter(DubbingJob.status == job_status)

    jobs = (
        query
        .order_by(desc(DubbingJob.created_at), desc(DubbingJob.id))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [build_job_response(job) for job in jobs]


@router.get("/stats", response_model=DubbingJobStats)
def get_dubbing_job_stats(
    db: Session = Depends(get_db),
) -> DubbingJobStats:
    """Return aggregate counts for all dubbing jobs."""
    counts = (
        db.query(
            func.count(DubbingJob.id).label("total_jobs"),
            func.sum(
                case(
                    (DubbingJob.status == JobStatus.QUEUED, 1),
                    else_=0,
                )
            ).label("queued_jobs"),
            func.sum(
                case(
                    (DubbingJob.status == JobStatus.PROCESSING, 1),
                    else_=0,
                )
            ).label("processing_jobs"),
            func.sum(
                case(
                    (DubbingJob.status == JobStatus.COMPLETED, 1),
                    else_=0,
                )
            ).label("completed_jobs"),
            func.sum(
                case(
                    (DubbingJob.status == JobStatus.FAILED, 1),
                    else_=0,
                )
            ).label("failed_jobs"),
            func.sum(
                case(
                    (DubbingJob.status == JobStatus.CANCELLED, 1),
                    else_=0,
                )
            ).label("cancelled_jobs"),
        )
        .one()
    )

    return DubbingJobStats(
        total_jobs=counts.total_jobs,
        queued_jobs=counts.queued_jobs or 0,
        processing_jobs=counts.processing_jobs or 0,
        completed_jobs=counts.completed_jobs or 0,
        failed_jobs=counts.failed_jobs or 0,
        cancelled_jobs=counts.cancelled_jobs or 0,
    )


@router.post(
    "/{job_id}/retry",
    response_model=DubbingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_dubbing_job(
    job_id: str,
    db: Session = Depends(get_db),
) -> DubbingJobResponse:
    """Retry a failed job and dispatch it to Celery."""
    updated_rows = (
        db.query(DubbingJob)
        .filter(
            DubbingJob.id == job_id,
            DubbingJob.status == JobStatus.FAILED,
        )
        .update(
            {
                DubbingJob.status: JobStatus.QUEUED,
                DubbingJob.progress: 0,
                DubbingJob.message: (
                    "Dubbing job retry accepted and queued for processing."
                ),
                DubbingJob.output_path: None,
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dubbing job not found",
            )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed jobs can be retried",
        )

    try:
        db.commit()

        job = db.get(DubbingJob, job_id)

        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dubbing job not found",
            )

        response = build_job_response(job)

    except Exception:
        db.rollback()
        raise

    try:
        process_dubbing_job.delay(job_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Job retry was saved, but the task could not be queued. "
                "Please check Redis and retry later."
            ),
        ) from exc

    return response


@router.post(
    "/{job_id}/cancel",
    response_model=DubbingJobResponse,
    status_code=status.HTTP_200_OK,
)
def cancel_dubbing_job(
    job_id: str,
    db: Session = Depends(get_db),
) -> DubbingJobResponse:
    """Cancel a queued dubbing job atomically."""
    updated_rows = (
        db.query(DubbingJob)
        .filter(
            DubbingJob.id == job_id,
            DubbingJob.status == JobStatus.QUEUED,
        )
        .update(
            {
                DubbingJob.status: JobStatus.CANCELLED,
                DubbingJob.progress: 0,
                DubbingJob.message: (
                    "Dubbing job cancelled before processing."
                ),
            },
            synchronize_session=False,
        )
    )

    if updated_rows == 0:
        db.rollback()

        job = db.get(DubbingJob, job_id)

        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dubbing job not found",
            )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only queued jobs can be cancelled",
        )

    try:
        db.commit()

        job = db.get(DubbingJob, job_id)

        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dubbing job not found",
            )

        return build_job_response(job)

    except Exception:
        db.rollback()
        raise


@router.get("/{job_id}/download")
def download_dubbing_output(
    job_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download the generated video for a completed job."""
    job = db.get(DubbingJob, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dubbing job not found",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Video is not available because the job is not completed"
            ),
        )

    if not job.output_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file path is not available",
        )

    output_file = Path(job.output_path).resolve()

    if not output_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output video file not found",
        )

    return FileResponse(
        path=str(output_file),
        media_type="video/mp4",
        filename=output_file.name,
    )


@router.post(
    "",
    response_model=DubbingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_dubbing_job(
    request: DubbingJobCreate,
    db: Session = Depends(get_db),
) -> DubbingJobResponse:
    """Create a dubbing job and dispatch it to Celery."""
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

    response = build_job_response(job)

    try:
        process_dubbing_job.delay(job.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Job was saved, but the task could not be queued. "
                "Please check Redis and retry later."
            ),
        ) from exc

    return response


@router.get("/{job_id}", response_model=DubbingJobResponse)
def get_dubbing_job(
    job_id: str,
    db: Session = Depends(get_db),
) -> DubbingJobResponse:
    """Get the current status of a dubbing job."""
    job = db.get(DubbingJob, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dubbing job not found",
        )

    return build_job_response(job)