from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import check_database_health, get_db

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Check service and database health",
    responses={
        200: {"description": "Service and database are healthy."},
        503: {"description": "Service is running, but database connectivity failed."},
    },
)
def health_check(db: Session = Depends(get_db)) -> JSONResponse:
    """Return service status and database connectivity without exposing internals."""
    if check_database_health(db):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "database": "connected"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "degraded", "database": "unavailable"},
    )
