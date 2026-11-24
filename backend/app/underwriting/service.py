from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import create_approval_request, record_audit_event
from app.core.auth import Actor
from app.core.config import Settings
from app.db.base import quantize_money
from app.db.models import ApprovalRequest, UnderwritingSubmission
from app.llm.router import LLMRouter
from app.underwriting.analyzer import evaluate_submission
from app.underwriting.schemas import SubmissionCreateIn, SubmissionOut, SubmissionReanalyzeIn


def serialize_submission(item: UnderwritingSubmission) -> SubmissionOut:
    return SubmissionOut(
        id=item.id,
        submission_number=item.submission_number,
        applicant_name=item.applicant_name,
        broker_name=item.broker_name,
        line_of_business=item.line_of_business,
        requested_effective_date=item.requested_effective_date,
        requested_limit=float(item.requested_limit),
        requested_deductible=float(item.requested_deductible),
        annual_revenue=float(item.annual_revenue),
        tiv_amount=float(item.tiv_amount),
        prior_premium=float(item.prior_premium),
        loss_history=item.loss_history_json,
        documents_submitted=item.documents_submitted_json,
        missing_documents=item.missing_documents_json,
        completeness_score=item.completeness_score,
        total_incurred_losses=float(item.total_incurred_losses),
        loss_count=item.loss_count,
        loss_ratio_pct=item.loss_ratio_pct,
        risk_score=item.risk_score,
        risk_tier=item.risk_tier,
        risk_factors=item.risk_factors_json,
        recommended_action=item.recommended_action,
        indicated_premium=float(item.indicated_premium),
        status=item.status,
        ai_risk_brief=item.ai_risk_brief,
        llm_provider_used=item.llm_provider_used,
        approval_id=item.approval_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def create_and_analyze_submission(
    db: AsyncSession,
    *,
    payload: SubmissionCreateIn,
    actor: Actor,
    llm_router: LLMRouter,
    settings: Settings,
) -> UnderwritingSubmission:
    """Ingest a commercial underwriting submission, score risk, and create HITL gate if required."""
    existing = (
        await db.execute(
            select(UnderwritingSubmission).where(
                UnderwritingSubmission.submission_number == payload.submission_number.strip()
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Submission '{payload.submission_number}' already exists.",
        )

    req_limit = quantize_money(payload.requested_limit)
    req_ded = quantize_money(payload.requested_deductible)
    rev = quantize_money(payload.annual_revenue)
    tiv = quantize_money(payload.tiv_amount)
    prior_prem = quantize_money(payload.prior_premium)
    losses_dicts = [entry.model_dump(mode="json") for entry in payload.loss_history]

    evaluation = evaluate_submission(
        line_of_business=payload.line_of_business,
        requested_limit=req_limit,
        requested_deductible=req_ded,
        tiv_amount=tiv,
        prior_premium=prior_prem,
        documents_submitted=payload.documents_submitted,
        loss_history=losses_dicts,
        settings=settings,
    )

    llm_res = await llm_router.generate(
        prompt=(
            f"Submission {payload.submission_number} ({payload.applicant_name}, "
            f"{evaluation.normalized_lob}): completeness {evaluation.completeness_score:.1f}%, "
            f"loss ratio {evaluation.loss_ratio_pct:.1f}%, risk score {evaluation.risk_score:.1f} "
            f"({evaluation.risk_tier}), indicated premium ${evaluation.indicated_premium:,.2f}, "
            f"action {evaluation.recommended_action}."
        ),
        system_prompt="Produce a concise commercial underwriting risk brief.",
        task_type="underwriting_brief",
    )

    submission = UnderwritingSubmission(
        submission_number=payload.submission_number.strip(),
        applicant_name=payload.applicant_name.strip(),
        broker_name=payload.broker_name.strip(),
        line_of_business=evaluation.normalized_lob,
        requested_effective_date=payload.requested_effective_date,
        requested_limit=req_limit,
        requested_deductible=req_ded,
        annual_revenue=rev,
        tiv_amount=tiv,
        prior_premium=prior_prem,
        loss_history_json=evaluation.normalized_losses,
        documents_submitted_json=evaluation.documents_submitted,
        missing_documents_json=evaluation.missing_documents,
        completeness_score=evaluation.completeness_score,
        total_incurred_losses=evaluation.total_incurred_losses,
        loss_count=evaluation.loss_count,
        loss_ratio_pct=evaluation.loss_ratio_pct,
        risk_score=evaluation.risk_score,
        risk_tier=evaluation.risk_tier,
        risk_factors_json=evaluation.risk_factors,
        recommended_action=evaluation.recommended_action,
        indicated_premium=evaluation.indicated_premium,
        status=evaluation.status,
        ai_risk_brief=llm_res.content,
        llm_provider_used=llm_res.provider,
    )
    db.add(submission)
    await db.flush()

    if evaluation.requires_hitl:
        approval = await create_approval_request(
            db,
            entity_type="underwriting_decision",
            entity_id=submission.id,
            action_requested=f"uw_{evaluation.recommended_action}",
            summary=(
                f"Underwriting {evaluation.recommended_action} for {submission.submission_number} "
                f"({submission.applicant_name}, tier {evaluation.risk_tier}, "
                f"limit ${float(req_limit):,.0f})"
            ),
            financial_exposure=req_limit,
            risk_level=evaluation.risk_level,
            requested_by=actor.email,
        )
        submission.approval_id = approval.id

    await record_audit_event(
        db,
        event_type="underwriting.analyzed",
        actor=actor,
        entity_type="underwriting_submission",
        entity_id=submission.id,
        action="analyzed",
        details={
            "submission_number": submission.submission_number,
            "applicant_name": submission.applicant_name,
            "completeness_score": submission.completeness_score,
            "loss_ratio_pct": submission.loss_ratio_pct,
            "risk_tier": submission.risk_tier,
            "recommended_action": submission.recommended_action,
        },
    )
    await db.commit()
    await db.refresh(submission)
    return submission


async def reanalyze_submission(
    db: AsyncSession,
    *,
    submission_id: str,
    payload: SubmissionReanalyzeIn,
    actor: Actor,
    llm_router: LLMRouter,
    settings: Settings,
) -> UnderwritingSubmission:
    """Merge supplemental documents/losses and recompute completeness and risk tier."""
    submission = await db.get(UnderwritingSubmission, submission_id)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission '{submission_id}' not found.",
        )

    merged_docs = list(submission.documents_submitted_json) + payload.documents_submitted
    merged_losses = list(submission.loss_history_json) + [
        entry.model_dump(mode="json") for entry in payload.additional_losses
    ]
    if payload.requested_limit is not None:
        submission.requested_limit = quantize_money(payload.requested_limit)
    if payload.requested_deductible is not None:
        submission.requested_deductible = quantize_money(payload.requested_deductible)

    evaluation = evaluate_submission(
        line_of_business=submission.line_of_business,
        requested_limit=quantize_money(submission.requested_limit),
        requested_deductible=quantize_money(submission.requested_deductible),
        tiv_amount=quantize_money(submission.tiv_amount),
        prior_premium=quantize_money(submission.prior_premium),
        documents_submitted=merged_docs,
        loss_history=merged_losses,
        settings=settings,
    )

    llm_res = await llm_router.generate(
        prompt=(
            f"Reanalyzed submission {submission.submission_number}: completeness "
            f"{evaluation.completeness_score:.1f}%, risk score {evaluation.risk_score:.1f} "
            f"({evaluation.risk_tier}), action {evaluation.recommended_action}."
        ),
        system_prompt="Produce an updated commercial underwriting risk brief.",
        task_type="underwriting_brief",
    )

    submission.documents_submitted_json = evaluation.documents_submitted
    submission.missing_documents_json = evaluation.missing_documents
    submission.completeness_score = evaluation.completeness_score
    submission.loss_history_json = evaluation.normalized_losses
    submission.total_incurred_losses = evaluation.total_incurred_losses
    submission.loss_count = evaluation.loss_count
    submission.loss_ratio_pct = evaluation.loss_ratio_pct
    submission.risk_score = evaluation.risk_score
    submission.risk_tier = evaluation.risk_tier
    submission.risk_factors_json = evaluation.risk_factors
    submission.recommended_action = evaluation.recommended_action
    submission.indicated_premium = evaluation.indicated_premium
    submission.ai_risk_brief = llm_res.content
    submission.llm_provider_used = llm_res.provider

    if submission.approval_id is not None:
        existing_app = await db.get(ApprovalRequest, submission.approval_id)
        if existing_app is not None and existing_app.status == "pending":
            existing_app.action_requested = f"uw_{evaluation.recommended_action}"
            existing_app.risk_level = evaluation.risk_level
            existing_app.summary = (
                f"Updated underwriting {evaluation.recommended_action} for "
                f"{submission.submission_number} (tier {evaluation.risk_tier})"
            )
    elif evaluation.requires_hitl:
        approval = await create_approval_request(
            db,
            entity_type="underwriting_decision",
            entity_id=submission.id,
            action_requested=f"uw_{evaluation.recommended_action}",
            summary=(
                f"Underwriting {evaluation.recommended_action} for {submission.submission_number} "
                f"({submission.applicant_name}, tier {evaluation.risk_tier})"
            ),
            financial_exposure=quantize_money(submission.requested_limit),
            risk_level=evaluation.risk_level,
            requested_by=actor.email,
        )
        submission.approval_id = approval.id

    submission.status = evaluation.status

    await record_audit_event(
        db,
        event_type="underwriting.reanalyzed",
        actor=actor,
        entity_type="underwriting_submission",
        entity_id=submission.id,
        action="reanalyzed",
        details={
            "submission_number": submission.submission_number,
            "completeness_score": submission.completeness_score,
            "risk_tier": submission.risk_tier,
            "recommended_action": submission.recommended_action,
        },
    )
    await db.commit()
    await db.refresh(submission)
    return submission
