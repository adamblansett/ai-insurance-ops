from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Actor, get_current_actor, require_roles
from app.core.config import Settings, get_settings
from app.db.models import UnderwritingSubmission
from app.db.session import get_db
from app.llm.router import LLMRouter, get_llm_router
from app.underwriting.schemas import SubmissionCreateIn, SubmissionOut, SubmissionReanalyzeIn
from app.underwriting.service import (
    create_and_analyze_submission,
    reanalyze_submission,
    serialize_submission,
)

router = APIRouter(prefix="/underwriting", tags=["underwriting"])


def _resolve_settings(request: Request, fallback: Settings) -> Settings:
    app_cfg = getattr(request.app.state, "settings", None)
    return app_cfg if isinstance(app_cfg, Settings) else fallback


@router.post("/submissions", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: SubmissionCreateIn,
    request: Request,
    actor: Actor = Depends(require_roles("underwriter", "claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    settings: Settings = Depends(get_settings),
) -> SubmissionOut:
    """Ingest and analyze a commercial underwriting submission."""
    cfg = _resolve_settings(request, settings)
    submission = await create_and_analyze_submission(
        db,
        payload=payload,
        actor=actor,
        llm_router=llm_router,
        settings=cfg,
    )
    return serialize_submission(submission)


@router.get("/submissions", response_model=list[SubmissionOut])
async def list_submissions(
    risk_tier: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    line_of_business: str | None = Query(default=None),
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[SubmissionOut]:
    """List underwriting submissions ordered newest first with optional filters."""
    stmt = select(UnderwritingSubmission).order_by(UnderwritingSubmission.created_at.desc())
    if risk_tier:
        stmt = stmt.where(UnderwritingSubmission.risk_tier == risk_tier.strip().lower())
    if status_filter:
        stmt = stmt.where(UnderwritingSubmission.status == status_filter.strip().lower())
    if line_of_business:
        stmt = stmt.where(
            UnderwritingSubmission.line_of_business == line_of_business.strip().lower()
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [serialize_submission(row) for row in rows]


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
async def get_submission(
    submission_id: str,
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> SubmissionOut:
    """Retrieve a single underwriting submission analysis."""
    submission = await db.get(UnderwritingSubmission, submission_id)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission '{submission_id}' not found.",
        )
    return serialize_submission(submission)


@router.post("/submissions/{submission_id}/reanalyze", response_model=SubmissionOut)
async def reanalyze_submission_endpoint(
    submission_id: str,
    payload: SubmissionReanalyzeIn,
    request: Request,
    actor: Actor = Depends(require_roles("underwriter", "claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    settings: Settings = Depends(get_settings),
) -> SubmissionOut:
    """Merge supplemental documents/losses and re-run underwriting risk evaluation."""
    cfg = _resolve_settings(request, settings)
    submission = await reanalyze_submission(
        db,
        submission_id=submission_id,
        payload=payload,
        actor=actor,
        llm_router=llm_router,
        settings=cfg,
    )
    return serialize_submission(submission)
