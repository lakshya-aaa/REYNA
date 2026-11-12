from fastapi import APIRouter

from app.api.v1.endpoints import activities, auth, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(activities.router)
