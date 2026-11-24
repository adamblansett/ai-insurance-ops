from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CoverageVerifyIn(BaseModel):
    """Request payload to run citation-grounded coverage verification."""

    claim_id: str
    policy_id: str | None = None


class CoverageVerificationOut(BaseModel):
    """Serialized coverage determination with limits, exclusions, and page citations."""

    id: str
    claim_id: str
    claim_number: str
    policy_id: str
    policy_number: str
    determination: str
    policy_in_force: bool
    applicable_limit: float
    applicable_deductible: float
    estimated_covered_payout: float
    excess_over_limit: float
    matched_clauses: list[dict[str, Any]]
    triggered_exclusions: list[dict[str, Any]]
    citations: list[str]
    confidence_score: float
    requires_hitl_review: bool
    status: str
    ai_rationale: str
    llm_provider_used: str
    approval_id: str | None
    created_at: datetime
    updated_at: datetime
