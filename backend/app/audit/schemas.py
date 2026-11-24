from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm.pii import RedactionFinding


class ApprovalRequestOut(BaseModel):
    """Serialized HITL approval gate record."""

    id: str
    entity_type: str
    entity_id: str
    action_requested: str
    summary: str
    financial_exposure: float
    risk_level: str
    status: str
    requested_by: str
    decided_by: str | None
    decision_notes: str | None
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecisionIn(BaseModel):
    """Human reviewer decision payload."""

    decision: Literal["approved", "rejected"]
    notes: str = Field(default="", max_length=1000)


class AuditEventOut(BaseModel):
    """Serialized immutable audit event entry."""

    id: str
    sequence_no: int
    event_type: str
    actor_email: str
    actor_role: str
    entity_type: str
    entity_id: str
    action: str
    details: dict[str, Any]
    prev_hash: str
    event_hash: str
    created_at: datetime


class AuditChainVerifyOut(BaseModel):
    """Cryptographic integrity verification summary for audit_events."""

    valid: bool
    total_events: int
    head_hash: str
    broken_sequence_no: int | None
    message: str


class PiiRedactIn(BaseModel):
    """Payload for interactive PII/PHI redaction preview."""

    text: str = Field(min_length=1, max_length=50000)


class PiiRedactOut(BaseModel):
    """PII/PHI redaction result returned to the console."""

    redacted_text: str
    findings: list[RedactionFinding]
    total_redactions: int
