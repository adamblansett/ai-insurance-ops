from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.overview import router as overview_router
from app.audit.router import router as audit_router
from app.claims.router import router as claims_router
from app.coverage.router import router as coverage_router
from app.intake.router import router as intake_router
from app.seed.router import router as seed_router
from app.underwriting.router import router as underwriting_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(overview_router)
api_v1_router.include_router(intake_router)
api_v1_router.include_router(claims_router)
api_v1_router.include_router(coverage_router)
api_v1_router.include_router(underwriting_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(seed_router)
