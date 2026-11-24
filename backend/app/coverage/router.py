from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Actor, get_current_actor, require_roles
from app.core.config import Settings, get_settings
from app.coverage.schemas import CoverageVerificationOut, CoverageVerifyIn
from app.coverage.service import run_coverage_verification, serialize_verification
from app.db.models import Claim, CoverageVerification, Policy
from app.db.session import get_db
from app.llm.router import LLMRouter, get_llm_router

router = APIRouter(prefix="/coverage", tags=["coverage"])


def _resolve_settings(request: Request, fallback: Settings) -> Settings:
    app_cfg = getattr(request.app.state, "settings", None)
    return app_cfg if isinstance(app_cfg, Settings) else fallback


@router.post("/verify", response_model=CoverageVerificationOut, status_code=status.HTTP_201_CREATED)
async def verify_coverage_endpoint(
    payload: CoverageVerifyIn,
    request: Request,
    actor: Actor = Depends(require_roles("adjuster", "claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    settings: Settings = Depends(get_settings),
) -> CoverageVerificationOut:
    """Verify claim facts against policy grants, endorsements, exclusions, and limits."""
    cfg = _resolve_settings(request, settings)
    verification, claim, policy = await run_coverage_verification(
        db,
        claim_id=payload.claim_id,
        policy_id=payload.policy_id,
        actor=actor,
        llm_router=llm_router,
        settings=cfg,
    )
    return serialize_verification(
        verification,
        claim_number=claim.claim_number,
        policy_number=policy.policy_number,
    )


@router.get("/verifications", response_model=list[CoverageVerificationOut])
async def list_verifications(
    claim_id: str | None = Query(default=None),
    determination: str | None = Query(default=None),
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[CoverageVerificationOut]:
    """List citation-grounded coverage verifications newest first."""
    stmt = (
        select(CoverageVerification, Claim.claim_number, Policy.policy_number)
        .join(Claim, Claim.id == CoverageVerification.claim_id)
        .join(Policy, Policy.id == CoverageVerification.policy_id)
        .order_by(CoverageVerification.created_at.desc())
    )
    if claim_id:
        stmt = stmt.where(CoverageVerification.claim_id == claim_id)
    if determination:
        stmt = stmt.where(CoverageVerification.determination == determination.strip().lower())
    rows = (await db.execute(stmt)).all()
    return [
        serialize_verification(ver, claim_number=claim_num, policy_number=pol_num)
        for ver, claim_num, pol_num in rows
    ]


@router.get("/verifications/{verification_id}", response_model=CoverageVerificationOut)
async def get_verification(
    verification_id: str,
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> CoverageVerificationOut:
    """Retrieve a single coverage verification record by ID."""
    stmt = (
        select(CoverageVerification, Claim.claim_number, Policy.policy_number)
        .join(Claim, Claim.id == CoverageVerification.claim_id)
        .join(Policy, Policy.id == CoverageVerification.policy_id)
        .where(CoverageVerification.id == verification_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coverage verification '{verification_id}' not found.",
        )
    ver, claim_num, pol_num = row
    return serialize_verification(ver, claim_number=claim_num, policy_number=pol_num)
