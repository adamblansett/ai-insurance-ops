from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, new_uuid, utcnow


class Policy(Base):
    """Ingested insurance policy declaration and metadata."""

    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    policy_number: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    carrier_name: Mapped[str] = mapped_column(String(200), default="Unknown Carrier")
    named_insured: Mapped[str] = mapped_column(String(240), index=True)
    insured_address: Mapped[str] = mapped_column(String(320), default="")
    line_of_business: Mapped[str] = mapped_column(String(80), index=True)
    acord_form_type: Mapped[str] = mapped_column(String(80), default="ACORD 140")
    effective_date: Mapped[date] = mapped_column(Date)
    expiration_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    per_occurrence_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    aggregate_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    deductible: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    annual_premium: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    source_filename: Mapped[str] = mapped_column(String(255), default="")
    content_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    extracted_schedules_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.9)
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    clauses: Mapped[list["PolicyClause"]] = relationship(
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="PolicyClause.page_number, PolicyClause.section_ref",
    )


class PolicyClause(Base):
    """Indexed coverage grant, exclusion, endorsement, sublimit, or condition clause."""

    __tablename__ = "policy_clauses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )
    clause_type: Mapped[str] = mapped_column(String(40), index=True)
    section_ref: Mapped[str] = mapped_column(String(120), default="Section I")
    page_number: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(240))
    clause_text: Mapped[str] = mapped_column(Text)
    monetary_limit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    deductible_override: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    embedding_json: Mapped[list[float]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    policy: Mapped[Policy] = relationship(back_populates="clauses")


class ApprovalRequest(Base):
    """Human-in-the-loop gate for high-exposure reserves, SIU referrals, coverage, and UW."""

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    action_requested: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(String(500))
    financial_exposure: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    risk_level: Mapped[str] = mapped_column(String(24), default="medium")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    requested_by: Mapped[str] = mapped_column(String(255))
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Claim(Base):
    """First Notice of Loss (FNOL) claim record with triage scoring and routing."""

    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    claim_number: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    policy_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    policy_number_reported: Mapped[str] = mapped_column(String(120), index=True)
    claimant_name: Mapped[str] = mapped_column(String(240))
    loss_date: Mapped[date] = mapped_column(Date)
    reported_date: Mapped[date] = mapped_column(Date)
    loss_location: Mapped[str] = mapped_column(String(240), default="")
    peril_type: Mapped[str] = mapped_column(String(64), index=True)
    loss_description: Mapped[str] = mapped_column(Text)
    claimed_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    injuries_reported: Mapped[bool] = mapped_column(Boolean, default=False)
    police_report_filed: Mapped[bool] = mapped_column(Boolean, default=False)
    severity_tier: Mapped[str] = mapped_column(String(32), index=True)
    reserve_band: Mapped[str] = mapped_column(String(48))
    recommended_reserve: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    adjuster_queue: Mapped[str] = mapped_column(String(64), index=True)
    fraud_score: Mapped[float] = mapped_column(Float, default=0.0)
    fraud_indicators_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    triage_status: Mapped[str] = mapped_column(String(40), default="triaged", index=True)
    ai_triage_summary: Mapped[str] = mapped_column(Text, default="")
    llm_provider_used: Mapped[str] = mapped_column(String(32), default="mock")
    approval_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CoverageVerification(Base):
    """Citation-grounded coverage determination matching a claim to policy clauses."""

    __tablename__ = "coverage_verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    claim_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )
    determination: Mapped[str] = mapped_column(String(48), index=True)
    policy_in_force: Mapped[bool] = mapped_column(Boolean, default=True)
    applicable_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    applicable_deductible: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    estimated_covered_payout: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00")
    )
    excess_over_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    matched_clauses_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    triggered_exclusions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    citations_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.85)
    requires_hitl_review: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="auto_verified", index=True)
    ai_rationale: Mapped[str] = mapped_column(Text, default="")
    llm_provider_used: Mapped[str] = mapped_column(String(32), default="mock")
    approval_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class UnderwritingSubmission(Base):
    """Commercial underwriting submission completeness, loss-run, and risk analysis."""

    __tablename__ = "underwriting_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    submission_number: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    applicant_name: Mapped[str] = mapped_column(String(240), index=True)
    broker_name: Mapped[str] = mapped_column(String(200), default="")
    line_of_business: Mapped[str] = mapped_column(String(80), index=True)
    requested_effective_date: Mapped[date] = mapped_column(Date)
    requested_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    requested_deductible: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    annual_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    tiv_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    prior_premium: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    loss_history_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    documents_submitted_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_documents_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    completeness_score: Mapped[float] = mapped_column(Float, default=0.0)
    total_incurred_losses: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00")
    )
    loss_count: Mapped[int] = mapped_column(Integer, default=0)
    loss_ratio_pct: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_tier: Mapped[str] = mapped_column(String(40), index=True)
    risk_factors_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    recommended_action: Mapped[str] = mapped_column(String(48))
    indicated_premium: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(40), default="analyzed", index=True)
    ai_risk_brief: Mapped[str] = mapped_column(Text, default="")
    llm_provider_used: Mapped[str] = mapped_column(String(32), default="mock")
    approval_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuditEvent(Base):
    """Immutable SHA-256 hash-chained insurance operations audit ledger."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    sequence_no: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_email: Mapped[str] = mapped_column(String(255))
    actor_role: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(80))
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestionJob(Base):
    """Asynchronous background policy ingestion job tracking."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_type: Mapped[str] = mapped_column(String(48), default="policy_upload")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    filename: Mapped[str] = mapped_column(String(255))
    policy_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("policies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_by: Mapped[str] = mapped_column(String(255))
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
