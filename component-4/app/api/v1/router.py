from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.submissions import router as submissions_router
from app.api.v1.verifications import router as verifications_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(submissions_router)
api_v1_router.include_router(verifications_router)
