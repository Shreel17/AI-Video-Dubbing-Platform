
from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return the API health status."""
    return {
        "status": "healthy",
        "service": "AI Video Dubbing Platform",
        "version": "1.0.0",
    }
