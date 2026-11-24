from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.service import create_approval_request, record_audit_event
from app.core.auth import Actor
from app.core.config import Settings
from app.coverage.schemas import CoverageVerificationOut
from app.coverage.verifier import evaluate_coverage
from app.db.models import Claim, CoverageVerification, Policy
from app.llm.router import LLMRouter


def serialize_verification(
    item: CoverageVerification,
    *,
    claim_number: str,
    policy_number: str,
) -> CoverageVerificationOut:
    return CoverageVerificationOut(
        id=item.id,
        claim_id=item.claim_id,
        claim_number=claim_number,
        policy_id=item.policy_id,
        policy_number=policy_number,
        determination=item.determination,
        policy_in_force=item.policy_in_force,
        applicable_limit=float(item.applicable_limit),
        applicable_deductible=float(item.applicable_deductible),
        estimated_covered_payout=float(item.estimated_covered_payout),
        excess_over_limit=float(item.excess_over_limit),
        matched_clauses=item.matched_clauses_json,
        triggered_exclusions=item.triggered_exclusions_json,
        citations=item.citations_json,
        confidence_score=item.confidence_score,
        requires_hitl_review=item.requires_hitl_review,
        status=item.status,
        ai_rationale=item.ai_rationale,
        llm_provider_used=item.llm_provider_used,
        approval_id=item.approval_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def run_coverage_verification(
    db: AsyncSession,
    *,
    claim_id: str,
    policy_id: str | None,
    actor: Actor,
    llm_router: LLMRouter,
    settings: Settings,
) -> tuple[CoverageVerification, Claim, Policy]:
    """Verify claim coverage against policy clauses, record citations, and raise HITL gate."""
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Claim '{claim_id}' not found.",
        )

    target_policy_id = policy_id or claim.policy_id
    policy: Policy | None = None
    if target_policy_id:
        policy = (
            await db.execute(
                select(Policy)
                .options(selectinload(Policy.clauses))
                .where(Policy.id == target_policy_id)
            )
        ).scalar_one_or_none()
    if policy is None and claim.policy_number_reported:
        policy = (
            await db.execute(
                select(Policy)
                .options(selectinload(Policy.clauses))
                .where(Policy.policy_number == claim.policy_number_reported)
            )
        ).scalar_one_or_none()

    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No ingested policy found for claim '{claim.claim_number}' "
                f"(reported '{claim.policy_number_reported}')."
            ),
        )

    if claim.policy_id != policy.id:
        claim.policy_id = policy.id

    evaluation = evaluate_coverage(
        claim=claim,
        policy=policy,
        clauses=list(policy.clauses),
        settings=settings,
    )

    llm_res = await llm_router.generate(
        prompt=(
            f"{evaluation.summary_rationale} Citations: "
            + "; ".join(evaluation.citations[:3])
        ),
        system_prompt="Produce a citation-grounded coverage verification memo.",
        task_type="coverage_verification",
    )
    rationale = f"{evaluation.summary_rationale} ({llm_res.content})"

    verification = CoverageVerification(
        claim_id=claim.id,
        policy_id=policy.id,
        determination=evaluation.determination,
        policy_in_force=evaluation.policy_in_force,
        applicable_limit=evaluation.applicable_limit,
        applicable_deductible=evaluation.applicable_deductible,
        estimated_covered_payout=evaluation.estimated_covered_payout,
        excess_over_limit=evaluation.excess_over_limit,
        matched_clauses_json=evaluation.matched_clauses,
        triggered_exclusions_json=evaluation.triggered_exclusions,
        citations_json=evaluation.citations,
        confidence_score=evaluation.confidence_score,
        requires_hitl_review=evaluation.requires_hitl_review,
        status=evaluation.status,
        ai_rationale=rationale,
        llm_provider_used=llm_res.provider,
    )
    db.add(verification)
    await db.flush()

    if evaluation.requires_hitl_review:
        risk_level = (
            "high"
            if evaluation.determination in ("excluded", "reservation_of_rights", "policy_inactive")
            else "medium"
        )
        approval = await create_approval_request(
            db,
            entity_type="coverage_determination",
            entity_id=verification.id,
            action_requested="approve_coverage_determination",
            summary=(
                f"Coverage {evaluation.determination} for {claim.claim_number} on "
                f"{policy.policy_number} "
                f"(payout ${float(evaluation.estimated_covered_payout):,.2f})"
            ),
            financial_exposure=evaluation.estimated_covered_payout,
            risk_level=risk_level,
            requested_by=actor.email,
        )
        verification.approval_id = approval.id

    await record_audit_event(
        db,
        event_type="coverage.verified",
        actor=actor,
        entity_type="coverage_verification",
        entity_id=verification.id,
        action="verified",
        details={
            "claim_number": claim.claim_number,
            "policy_number": policy.policy_number,
            "determination": verification.determination,
            "estimated_covered_payout": float(verification.estimated_covered_payout),
            "requires_hitl_review": verification.requires_hitl_review,
            "citations_count": len(verification.citations_json),
        },
    )
    await db.commit()
    await db.refresh(verification)
    return verification, claim, policy
