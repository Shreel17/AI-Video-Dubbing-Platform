
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API for managing automated video dubbing workflows.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    health_router,
    prefix=settings.api_prefix,
)

app.include_router(
    jobs_router,
    prefix=settings.api_prefix,
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": f"Welcome to the {settings.app_name} API",
        "environment": settings.environment,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
