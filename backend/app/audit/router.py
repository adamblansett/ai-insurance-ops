from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import (
    ApprovalDecisionIn,
    ApprovalRequestOut,
    AuditChainVerifyOut,
    AuditEventOut,
    PiiRedactIn,
    PiiRedactOut,
)
from app.audit.service import decide_approval, verify_audit_chain
from app.core.auth import Actor, get_current_actor, require_roles
from app.db.models import ApprovalRequest, AuditEvent
from app.db.session import get_db
from app.llm.pii import redact_pii

router = APIRouter(prefix="/audit", tags=["audit"])


def _serialize_approval(item: ApprovalRequest) -> ApprovalRequestOut:
    return ApprovalRequestOut(
        id=item.id,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        action_requested=item.action_requested,
        summary=item.summary,
        financial_exposure=float(item.financial_exposure),
        risk_level=item.risk_level,
        status=item.status,
        requested_by=item.requested_by,
        decided_by=item.decided_by,
        decision_notes=item.decision_notes,
        created_at=item.created_at,
        decided_at=item.decided_at,
    )


def _serialize_event(item: AuditEvent) -> AuditEventOut:
    return AuditEventOut(
        id=item.id,
        sequence_no=item.sequence_no,
        event_type=item.event_type,
        actor_email=item.actor_email,
        actor_role=item.actor_role,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        action=item.action,
        details=item.details_json,
        prev_hash=item.prev_hash,
        event_hash=item.event_hash,
        created_at=item.created_at,
    )


@router.get("/approvals", response_model=list[ApprovalRequestOut])
async def list_approvals(
    status_filter: str | None = Query(default=None, alias="status"),
    entity_type: str | None = Query(default=None),
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequestOut]:
    """List HITL approval requests sorted newest first."""
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    if status_filter:
        stmt = stmt.where(ApprovalRequest.status == status_filter.strip().lower())
    if entity_type:
        stmt = stmt.where(ApprovalRequest.entity_type == entity_type.strip().lower())
    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize_approval(row) for row in rows]


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalRequestOut)
async def decide_approval_endpoint(
    approval_id: str,
    payload: ApprovalDecisionIn,
    actor: Actor = Depends(require_roles("underwriter", "claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestOut:
    """Approve or reject a pending HITL approval request."""
    updated = await decide_approval(
        db,
        approval_id=approval_id,
        decision=payload.decision,
        notes=payload.notes,
        actor=actor,
    )
    return _serialize_approval(updated)


@router.get("/events", response_model=list[AuditEventOut])
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[AuditEventOut]:
    """Return immutable audit trail events in reverse chronological sequence."""
    stmt = select(AuditEvent).order_by(AuditEvent.sequence_no.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize_event(row) for row in rows]


@router.get("/events/verify", response_model=AuditChainVerifyOut)
async def verify_audit_chain_endpoint(
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> AuditChainVerifyOut:
    """Verify the cryptographic SHA-256 chain integrity of all audit events."""
    return await verify_audit_chain(db)


@router.post("/pii/redact", response_model=PiiRedactOut)
async def preview_pii_redaction(
    payload: PiiRedactIn,
    _: Actor = Depends(get_current_actor),
) -> PiiRedactOut:
    """Preview PII/PHI scrubbing applied before outbound cloud LLM calls."""
    result = redact_pii(payload.text)
    return PiiRedactOut(
        redacted_text=result.redacted_text,
        findings=result.findings,
        total_redactions=result.total_redactions,
    )
