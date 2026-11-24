from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import create_approval_request, record_audit_event
from app.claims.schemas import ClaimCreateIn, ClaimOut
from app.claims.triage import evaluate_fnol_triage
from app.core.auth import Actor
from app.core.config import Settings
from app.db.base import quantize_money
from app.db.models import Claim, Policy
from app.llm.router import LLMRouter


def serialize_claim(claim: Claim) -> ClaimOut:
    return ClaimOut(
        id=claim.id,
        claim_number=claim.claim_number,
        policy_id=claim.policy_id,
        policy_number_reported=claim.policy_number_reported,
        claimant_name=claim.claimant_name,
        loss_date=claim.loss_date,
        reported_date=claim.reported_date,
        loss_location=claim.loss_location,
        peril_type=claim.peril_type,
        loss_description=claim.loss_description,
        claimed_amount=float(claim.claimed_amount),
        injuries_reported=claim.injuries_reported,
        police_report_filed=claim.police_report_filed,
        severity_tier=claim.severity_tier,
        reserve_band=claim.reserve_band,
        recommended_reserve=float(claim.recommended_reserve),
        adjuster_queue=claim.adjuster_queue,
        fraud_score=claim.fraud_score,
        fraud_indicators=claim.fraud_indicators_json,
        triage_status=claim.triage_status,
        ai_triage_summary=claim.ai_triage_summary,
        llm_provider_used=claim.llm_provider_used,
        approval_id=claim.approval_id,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )


async def submit_and_triage_claim(
    db: AsyncSession,
    *,
    payload: ClaimCreateIn,
    actor: Actor,
    llm_router: LLMRouter,
    settings: Settings,
) -> Claim:
    """Create a FNOL claim, run triage scoring, create HITL approval if needed, and audit."""
    existing = (
        await db.execute(select(Claim).where(Claim.claim_number == payload.claim_number.strip()))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Claim '{payload.claim_number}' already exists.",
        )

    policy = (
        await db.execute(
            select(Policy).where(Policy.policy_number == payload.policy_number_reported.strip())
        )
    ).scalar_one_or_none()
    prior_claims = list(
        (
            await db.execute(
                select(Claim).where(
                    Claim.policy_number_reported == payload.policy_number_reported.strip()
                )
            )
        )
        .scalars()
        .all()
    )

    claimed_dec = quantize_money(payload.claimed_amount)
    decision = evaluate_fnol_triage(
        claim_number=payload.claim_number.strip(),
        loss_date=payload.loss_date,
        reported_date=payload.reported_date,
        peril_type=payload.peril_type,
        loss_description=payload.loss_description,
        claimed_amount=claimed_dec,
        injuries_reported=payload.injuries_reported,
        police_report_filed=payload.police_report_filed,
        policy=policy,
        existing_claims=prior_claims,
        settings=settings,
    )

    llm_res = await llm_router.generate(
        prompt=(
            f"Claim {payload.claim_number} ({decision.normalized_peril}) for "
            f"{payload.claimant_name}: claimed ${claimed_dec:,.2f}, severity "
            f"{decision.severity_tier}, reserve ${decision.recommended_reserve:,.2f}, "
            f"queue {decision.adjuster_queue}, fraud_score {decision.fraud_score:.2f}."
        ),
        system_prompt="Produce a concise claims adjuster triage note.",
        task_type="claims_triage",
    )

    claim = Claim(
        claim_number=payload.claim_number.strip(),
        policy_id=policy.id if policy is not None else None,
        policy_number_reported=payload.policy_number_reported.strip(),
        claimant_name=payload.claimant_name.strip(),
        loss_date=payload.loss_date,
        reported_date=payload.reported_date,
        loss_location=payload.loss_location.strip(),
        peril_type=decision.normalized_peril,
        loss_description=payload.loss_description.strip(),
        claimed_amount=claimed_dec,
        injuries_reported=payload.injuries_reported,
        police_report_filed=payload.police_report_filed,
        severity_tier=decision.severity_tier,
        reserve_band=decision.reserve_band,
        recommended_reserve=decision.recommended_reserve,
        adjuster_queue=decision.adjuster_queue,
        fraud_score=decision.fraud_score,
        fraud_indicators_json=decision.fraud_indicators,
        triage_status=decision.triage_status,
        ai_triage_summary=llm_res.content,
        llm_provider_used=llm_res.provider,
    )
    db.add(claim)
    await db.flush()

    if decision.requires_hitl and decision.approval_entity_type and decision.approval_action:
        summary_msg = (
            f"SIU referral review for {claim.claim_number} (fraud score {claim.fraud_score:.2f})"
            if decision.approval_entity_type == "siu_referral"
            else (
                f"Reserve authority ${float(claim.recommended_reserve):,.2f} for "
                f"{claim.claim_number} ({claim.peril_type})"
            )
        )
        approval = await create_approval_request(
            db,
            entity_type=decision.approval_entity_type,
            entity_id=claim.id,
            action_requested=decision.approval_action,
            summary=summary_msg,
            financial_exposure=claim.recommended_reserve,
            risk_level=decision.risk_level,
            requested_by=actor.email,
        )
        claim.approval_id = approval.id

    await record_audit_event(
        db,
        event_type="claim.triaged",
        actor=actor,
        entity_type="claim",
        entity_id=claim.id,
        action="triaged",
        details={
            "claim_number": claim.claim_number,
            "peril_type": claim.peril_type,
            "severity_tier": claim.severity_tier,
            "recommended_reserve": float(claim.recommended_reserve),
            "fraud_score": claim.fraud_score,
            "adjuster_queue": claim.adjuster_queue,
            "triage_status": claim.triage_status,
        },
    )
    await db.commit()
    await db.refresh(claim)
    return claim


async def retriage_claim(
    db: AsyncSession,
    *,
    claim_id: str,
    actor: Actor,
    llm_router: LLMRouter,
    settings: Settings,
) -> Claim:
    """Re-run policy linking and FNOL triage scoring for an existing claim."""
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Claim '{claim_id}' not found.",
        )

    policy = (
        await db.execute(
            select(Policy).where(Policy.policy_number == claim.policy_number_reported)
        )
    ).scalar_one_or_none()
    prior_claims = list(
        (
            await db.execute(
                select(Claim).where(
                    Claim.policy_number_reported == claim.policy_number_reported,
                    Claim.id != claim.id,
                )
            )
        )
        .scalars()
        .all()
    )

    decision = evaluate_fnol_triage(
        claim_number=claim.claim_number,
        loss_date=claim.loss_date,
        reported_date=claim.reported_date,
        peril_type=claim.peril_type,
        loss_description=claim.loss_description,
        claimed_amount=quantize_money(claim.claimed_amount),
        injuries_reported=claim.injuries_reported,
        police_report_filed=claim.police_report_filed,
        policy=policy,
        existing_claims=prior_claims,
        settings=settings,
    )

    linked_label = policy.policy_number if policy else "none"
    llm_res = await llm_router.generate(
        prompt=(
            f"Retriage claim {claim.claim_number}: linked_policy={linked_label}, "
            f"severity={decision.severity_tier}, reserve=${decision.recommended_reserve:,.2f}, "
            f"fraud_score={decision.fraud_score:.2f}."
        ),
        system_prompt="Produce a concise claims adjuster retriage update.",
        task_type="claims_triage",
    )

    claim.policy_id = policy.id if policy is not None else None
    claim.peril_type = decision.normalized_peril
    claim.severity_tier = decision.severity_tier
    claim.reserve_band = decision.reserve_band
    claim.recommended_reserve = decision.recommended_reserve
    claim.adjuster_queue = decision.adjuster_queue
    claim.fraud_score = decision.fraud_score
    claim.fraud_indicators_json = decision.fraud_indicators
    claim.ai_triage_summary = llm_res.content
    claim.llm_provider_used = llm_res.provider

    if claim.approval_id is None and decision.requires_hitl and decision.approval_entity_type:
        claim.triage_status = decision.triage_status
        approval = await create_approval_request(
            db,
            entity_type=decision.approval_entity_type,
            entity_id=claim.id,
            action_requested=decision.approval_action or "approve_reserve_authority",
            summary=(
                f"Retriage review for {claim.claim_number} "
                f"(reserve ${float(claim.recommended_reserve):,.2f}, fraud {claim.fraud_score:.2f})"
            ),
            financial_exposure=claim.recommended_reserve,
            risk_level=decision.risk_level,
            requested_by=actor.email,
        )
        claim.approval_id = approval.id
    elif claim.approval_id is None:
        claim.triage_status = decision.triage_status

    await record_audit_event(
        db,
        event_type="claim.retriaged",
        actor=actor,
        entity_type="claim",
        entity_id=claim.id,
        action="retriaged",
        details={
            "claim_number": claim.claim_number,
            "policy_id": claim.policy_id,
            "fraud_score": claim.fraud_score,
            "recommended_reserve": float(claim.recommended_reserve),
        },
    )
    await db.commit()
    await db.refresh(claim)
    return claim
