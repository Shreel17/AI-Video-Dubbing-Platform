import shutil
from uuid import uuid4
from pathlib import Path
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse,JSONResponse
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

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB

ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
}

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


@router.get("/{job_id}/quality-report")
def get_quality_report(
    job_id: str,
    db: Session = Depends(get_db),
):
    """Return the automated quality report for a completed dubbing job."""
    job = db.get(DubbingJob, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dubbing job not found",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quality report is available only for completed jobs",
        )

    if not job.output_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output video path is not available",
        )

    output_file = Path(job.output_path)
    report_file = output_file.parent / "quality_report.json"

    if not report_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quality report not found for this job",
        )

    try:
        import json

        with report_file.open("r", encoding="utf-8") as file:
            report = json.load(file)
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Quality report could not be read",
        )

    return JSONResponse(content=report)


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


@router.post(
    "/upload",
    response_model=DubbingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_dubbing_job(
    file: UploadFile = File(...),
    target_language: str = Form(default="en"),
    source_language: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> DubbingJobResponse:
    """Upload a local video and queue a dubbing job."""
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported video format. Use MP4, MOV, MKV, AVI, or WEBM."
            ),
        )

    # Validate languages using the same rules as the main pipeline.
    from main import validate_target_language

    try:
        target_language = validate_target_language(target_language)

        if source_language is not None:
            source_language = source_language.strip().lower()

            if (
                len(source_language) < 2
                or len(source_language) > 10
            ):
                raise ValueError("Invalid source language code.")

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    job_id = str(uuid4())
    upload_path = UPLOAD_DIR / f"{job_id}{suffix}"
    total_size = 0

    try:
        with upload_path.open("wb") as destination:
            while True:
                chunk = file.file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Video exceeds the 500 MB upload limit.",
                    )

                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is empty.",
            )

        job = DubbingJob(
            id=job_id,
            video_url=str(upload_path.resolve()),
            source_language=source_language,
            target_language=target_language,
            status=JobStatus.QUEUED,
            progress=0,
            message="Uploaded video accepted and queued for processing.",
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
                    "Upload was saved, but the task could not be queued. "
                    "Check Redis and retry later."
                ),
            ) from exc

        return response

    except Exception:
        db.rollback()

        # Do not delete the file after the job has been saved:
        # it may already be queued for processing.
        if db.get(DubbingJob, job_id) is None and upload_path.exists():
            upload_path.unlink(missing_ok=True)

        raise

    finally:
        file.file.close()
