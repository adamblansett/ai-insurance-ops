from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.claims.schemas import ClaimCreateIn, ClaimOut
from app.claims.service import retriage_claim, serialize_claim, submit_and_triage_claim
from app.core.auth import Actor, get_current_actor, require_roles
from app.core.config import Settings, get_settings
from app.db.models import Claim
from app.db.session import get_db
from app.llm.router import LLMRouter, get_llm_router

router = APIRouter(prefix="/claims", tags=["claims"])


def _resolve_settings(request: Request, fallback: Settings) -> Settings:
    app_cfg = getattr(request.app.state, "settings", None)
    return app_cfg if isinstance(app_cfg, Settings) else fallback


@router.post("", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def create_claim(
    payload: ClaimCreateIn,
    request: Request,
    actor: Actor = Depends(require_roles("adjuster", "claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    settings: Settings = Depends(get_settings),
) -> ClaimOut:
    """Submit a FNOL claim and run automated severity, reserve, and fraud triage."""
    cfg = _resolve_settings(request, settings)
    claim = await submit_and_triage_claim(
        db,
        payload=payload,
        actor=actor,
        llm_router=llm_router,
        settings=cfg,
    )
    return serialize_claim(claim)


@router.get("", response_model=list[ClaimOut])
async def list_claims(
    triage_status: str | None = Query(default=None),
    severity_tier: str | None = Query(default=None),
    adjuster_queue: str | None = Query(default=None),
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ClaimOut]:
    """List FNOL claims ordered newest first with optional queue and severity filters."""
    stmt = select(Claim).order_by(Claim.created_at.desc())
    if triage_status:
        stmt = stmt.where(Claim.triage_status == triage_status.strip().lower())
    if severity_tier:
        stmt = stmt.where(Claim.severity_tier == severity_tier.strip().lower())
    if adjuster_queue:
        stmt = stmt.where(Claim.adjuster_queue == adjuster_queue.strip().lower())
    rows = (await db.execute(stmt)).scalars().all()
    return [serialize_claim(row) for row in rows]


@router.get("/{claim_id}", response_model=ClaimOut)
async def get_claim(
    claim_id: str,
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> ClaimOut:
    """Retrieve a single claim by ID."""
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Claim '{claim_id}' not found.",
        )
    return serialize_claim(claim)


@router.post("/{claim_id}/retriage", response_model=ClaimOut)
async def retriage_claim_endpoint(
    claim_id: str,
    request: Request,
    actor: Actor = Depends(require_roles("adjuster", "claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    settings: Settings = Depends(get_settings),
) -> ClaimOut:
    """Re-run policy linking and triage scoring for an existing claim."""
    cfg = _resolve_settings(request, settings)
    claim = await retriage_claim(
        db,
        claim_id=claim_id,
        actor=actor,
        llm_router=llm_router,
        settings=cfg,
    )
    return serialize_claim(claim)
