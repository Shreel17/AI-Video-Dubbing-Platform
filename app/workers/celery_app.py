import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

broker_url = os.getenv(
    "CELERY_BROKER_URL",
    "redis://localhost:6379/0",
)

celery_app = Celery(
    "dubbing_platform",
    broker=broker_url,
    backend=broker_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
