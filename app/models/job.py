from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.schemas.job import JobStatus


class DubbingJob(Base):
    __tablename__ = "dubbing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_url: Mapped[str] = mapped_column(Text, nullable=False)

    source_language: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    target_language: Mapped[str] = mapped_column(
        String(10), nullable=False
    )

    status: Mapped[JobStatus] = mapped_column(
        SQLAlchemyEnum(
            JobStatus,
            name="dubbing_job_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=JobStatus.QUEUED,
        nullable=False,
    )

    progress: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    message: Mapped[str] = mapped_column(
        Text, default="Job created", nullable=False
    )
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_time_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
