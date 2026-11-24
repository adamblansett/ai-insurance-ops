"""Initial AI Insurance Operations Phase 1 schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-24 18:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("policy_number", sa.String(length=120), nullable=False),
        sa.Column("carrier_name", sa.String(length=200), nullable=False),
        sa.Column("named_insured", sa.String(length=240), nullable=False),
        sa.Column("insured_address", sa.String(length=320), nullable=False),
        sa.Column("line_of_business", sa.String(length=80), nullable=False),
        sa.Column("acord_form_type", sa.String(length=80), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("per_occurrence_limit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("aggregate_limit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("deductible", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("annual_premium", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("extracted_schedules_json", sa.JSON(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_number"),
    )
    op.create_index("ix_policies_policy_number", "policies", ["policy_number"], unique=True)
    op.create_index("ix_policies_named_insured", "policies", ["named_insured"])
    op.create_index("ix_policies_line_of_business", "policies", ["line_of_business"])
    op.create_index("ix_policies_status", "policies", ["status"])
    op.create_index("ix_policies_content_sha256", "policies", ["content_sha256"])

    op.create_table(
        "policy_clauses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("policy_id", sa.String(length=36), nullable=False),
        sa.Column("clause_type", sa.String(length=40), nullable=False),
        sa.Column("section_ref", sa.String(length=120), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("clause_text", sa.Text(), nullable=False),
        sa.Column("monetary_limit", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("deductible_override", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("keywords_json", sa.JSON(), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_clauses_policy_id", "policy_clauses", ["policy_id"])
    op.create_index("ix_policy_clauses_clause_type", "policy_clauses", ["clause_type"])

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("action_requested", sa.String(length=100), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("financial_exposure", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("risk_level", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("decided_by", sa.String(length=255), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_entity_type", "approval_requests", ["entity_type"])
    op.create_index("ix_approval_requests_entity_id", "approval_requests", ["entity_id"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])

    op.create_table(
        "claims",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("claim_number", sa.String(length=120), nullable=False),
        sa.Column("policy_id", sa.String(length=36), nullable=True),
        sa.Column("policy_number_reported", sa.String(length=120), nullable=False),
        sa.Column("claimant_name", sa.String(length=240), nullable=False),
        sa.Column("loss_date", sa.Date(), nullable=False),
        sa.Column("reported_date", sa.Date(), nullable=False),
        sa.Column("loss_location", sa.String(length=240), nullable=False),
        sa.Column("peril_type", sa.String(length=64), nullable=False),
        sa.Column("loss_description", sa.Text(), nullable=False),
        sa.Column("claimed_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("injuries_reported", sa.Boolean(), nullable=False),
        sa.Column("police_report_filed", sa.Boolean(), nullable=False),
        sa.Column("severity_tier", sa.String(length=32), nullable=False),
        sa.Column("reserve_band", sa.String(length=48), nullable=False),
        sa.Column("recommended_reserve", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("adjuster_queue", sa.String(length=64), nullable=False),
        sa.Column("fraud_score", sa.Float(), nullable=False),
        sa.Column("fraud_indicators_json", sa.JSON(), nullable=False),
        sa.Column("triage_status", sa.String(length=40), nullable=False),
        sa.Column("ai_triage_summary", sa.Text(), nullable=False),
        sa.Column("llm_provider_used", sa.String(length=32), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_number"),
    )
    op.create_index("ix_claims_claim_number", "claims", ["claim_number"], unique=True)
    op.create_index("ix_claims_policy_id", "claims", ["policy_id"])
    op.create_index("ix_claims_policy_number_reported", "claims", ["policy_number_reported"])
    op.create_index("ix_claims_peril_type", "claims", ["peril_type"])
    op.create_index("ix_claims_severity_tier", "claims", ["severity_tier"])
    op.create_index("ix_claims_adjuster_queue", "claims", ["adjuster_queue"])
    op.create_index("ix_claims_triage_status", "claims", ["triage_status"])

    op.create_table(
        "coverage_verifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        sa.Column("policy_id", sa.String(length=36), nullable=False),
        sa.Column("determination", sa.String(length=48), nullable=False),
        sa.Column("policy_in_force", sa.Boolean(), nullable=False),
        sa.Column("applicable_limit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("applicable_deductible", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("estimated_covered_payout", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("excess_over_limit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("matched_clauses_json", sa.JSON(), nullable=False),
        sa.Column("triggered_exclusions_json", sa.JSON(), nullable=False),
        sa.Column("citations_json", sa.JSON(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("requires_hitl_review", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("ai_rationale", sa.Text(), nullable=False),
        sa.Column("llm_provider_used", sa.String(length=32), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coverage_verifications_claim_id", "coverage_verifications", ["claim_id"])
    op.create_index("ix_coverage_verifications_policy_id", "coverage_verifications", ["policy_id"])
    op.create_index(
        "ix_coverage_verifications_determination", "coverage_verifications", ["determination"]
    )
    op.create_index("ix_coverage_verifications_status", "coverage_verifications", ["status"])

    op.create_table(
        "underwriting_submissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("submission_number", sa.String(length=120), nullable=False),
        sa.Column("applicant_name", sa.String(length=240), nullable=False),
        sa.Column("broker_name", sa.String(length=200), nullable=False),
        sa.Column("line_of_business", sa.String(length=80), nullable=False),
        sa.Column("requested_effective_date", sa.Date(), nullable=False),
        sa.Column("requested_limit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("requested_deductible", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("annual_revenue", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("tiv_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("prior_premium", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("loss_history_json", sa.JSON(), nullable=False),
        sa.Column("documents_submitted_json", sa.JSON(), nullable=False),
        sa.Column("missing_documents_json", sa.JSON(), nullable=False),
        sa.Column("completeness_score", sa.Float(), nullable=False),
        sa.Column("total_incurred_losses", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("loss_count", sa.Integer(), nullable=False),
        sa.Column("loss_ratio_pct", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_tier", sa.String(length=40), nullable=False),
        sa.Column("risk_factors_json", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.String(length=48), nullable=False),
        sa.Column("indicated_premium", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("ai_risk_brief", sa.Text(), nullable=False),
        sa.Column("llm_provider_used", sa.String(length=32), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_number"),
    )
    op.create_index(
        "ix_underwriting_submissions_submission_number",
        "underwriting_submissions",
        ["submission_number"],
        unique=True,
    )
    op.create_index(
        "ix_underwriting_submissions_applicant_name",
        "underwriting_submissions",
        ["applicant_name"],
    )
    op.create_index(
        "ix_underwriting_submissions_line_of_business",
        "underwriting_submissions",
        ["line_of_business"],
    )
    op.create_index(
        "ix_underwriting_submissions_risk_tier", "underwriting_submissions", ["risk_tier"]
    )
    op.create_index("ix_underwriting_submissions_status", "underwriting_submissions", ["status"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor_email", sa.String(length=255), nullable=False),
        sa.Column("actor_role", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sequence_no"),
    )
    op.create_index("ix_audit_events_sequence_no", "audit_events", ["sequence_no"], unique=True)
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_entity_type", "audit_events", ["entity_type"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("underwriting_submissions")
    op.drop_table("coverage_verifications")
    op.drop_table("claims")
    op.drop_table("approval_requests")
    op.drop_table("policy_clauses")
    op.drop_table("policies")
