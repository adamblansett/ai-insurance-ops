from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import verify_audit_chain
from app.core.auth import Actor, get_current_actor
from app.db.models import (
    ApprovalRequest,
    AuditEvent,
    Claim,
    CoverageVerification,
    Policy,
    PolicyClause,
    UnderwritingSubmission,
)
from app.db.session import get_db

router = APIRouter(prefix="/overview", tags=["overview"])


class OverviewSummaryOut(BaseModel):
    """Executive KPI summary across policy intake, claims, coverage, UW, and audit."""

    policies_count: int
    indexed_clauses_count: int
    total_insured_limit: float
    claims_count: int
    total_recommended_reserves: float
    siu_flagged_claims_count: int
    verifications_count: int
    excluded_or_ror_count: int
    total_estimated_payout: float
    submissions_count: int
    avg_loss_ratio_pct: float
    pending_approvals_count: int
    audit_events_count: int
    audit_chain_valid: bool


@router.get("", response_model=OverviewSummaryOut)
async def get_overview(
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> OverviewSummaryOut:
    """Return aggregated KPIs across all AI Insurance Operations modules."""
    policies_count = int((await db.execute(select(func.count(Policy.id)))).scalar() or 0)
    clauses_count = int((await db.execute(select(func.count(PolicyClause.id)))).scalar() or 0)
    total_limit = float(
        (await db.execute(select(func.coalesce(func.sum(Policy.per_occurrence_limit), 0)))).scalar()
        or 0.0
    )

    claims_count = int((await db.execute(select(func.count(Claim.id)))).scalar() or 0)
    total_reserves = float(
        (
            await db.execute(select(func.coalesce(func.sum(Claim.recommended_reserve), 0)))
        ).scalar()
        or 0.0
    )
    siu_count = int(
        (
            await db.execute(
                select(func.count(Claim.id)).where(
                    Claim.adjuster_queue == "siu_investigation"
                )
            )
        ).scalar()
        or 0
    )

    verifications_count = int(
        (await db.execute(select(func.count(CoverageVerification.id)))).scalar() or 0
    )
    excluded_or_ror_count = int(
        (
            await db.execute(
                select(func.count(CoverageVerification.id)).where(
                    CoverageVerification.determination.in_(
                        ("excluded", "reservation_of_rights", "policy_inactive")
                    )
                )
            )
        ).scalar()
        or 0
    )
    total_payout = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(CoverageVerification.estimated_covered_payout), 0))
            )
        ).scalar()
        or 0.0
    )

    submissions_count = int(
        (await db.execute(select(func.count(UnderwritingSubmission.id)))).scalar() or 0
    )
    avg_loss_ratio = float(
        (
            await db.execute(
                select(func.coalesce(func.avg(UnderwritingSubmission.loss_ratio_pct), 0))
            )
        ).scalar()
        or 0.0
    )

    pending_approvals_count = int(
        (
            await db.execute(
                select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == "pending")
            )
        ).scalar()
        or 0
    )
    audit_events_count = int((await db.execute(select(func.count(AuditEvent.id)))).scalar() or 0)
    chain_check = await verify_audit_chain(db)

    return OverviewSummaryOut(
        policies_count=policies_count,
        indexed_clauses_count=clauses_count,
        total_insured_limit=round(total_limit, 2),
        claims_count=claims_count,
        total_recommended_reserves=round(total_reserves, 2),
        siu_flagged_claims_count=siu_count,
        verifications_count=verifications_count,
        excluded_or_ror_count=excluded_or_ror_count,
        total_estimated_payout=round(total_payout, 2),
        submissions_count=submissions_count,
        avg_loss_ratio_pct=round(avg_loss_ratio, 2),
        pending_approvals_count=pending_approvals_count,
        audit_events_count=audit_events_count,
        audit_chain_valid=chain_check.valid,
    )
