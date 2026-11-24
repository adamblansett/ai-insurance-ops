from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LossRunEntryIn(BaseModel):
    """Historical claim entry on a 3- or 5-year loss run."""

    loss_date: date
    claim_number: str = ""
    peril: str = "other"
    status: Literal["open", "closed", "reopened"] = "closed"
    paid_amount: float = Field(default=0.0, ge=0)
    reserve_amount: float = Field(default=0.0, ge=0)
    incurred_amount: float | None = Field(default=None, ge=0)
    description: str = ""


class SubmissionCreateIn(BaseModel):
    """Commercial underwriting submission intake payload."""

    submission_number: str = Field(min_length=3, max_length=120)
    applicant_name: str = Field(min_length=2, max_length=240)
    broker_name: str = Field(default="", max_length=200)
    line_of_business: str = Field(default="commercial_property", max_length=80)
    requested_effective_date: date
    requested_limit: float = Field(gt=0)
    requested_deductible: float = Field(default=5000.0, ge=0)
    annual_revenue: float = Field(default=0.0, ge=0)
    tiv_amount: float = Field(default=0.0, ge=0)
    prior_premium: float = Field(default=0.0, ge=0)
    documents_submitted: list[str] = Field(default_factory=list)
    loss_history: list[LossRunEntryIn] = Field(default_factory=list)


class SubmissionReanalyzeIn(BaseModel):
    """Optional supplemental documents or losses when re-evaluating a submission."""

    documents_submitted: list[str] = Field(default_factory=list)
    additional_losses: list[LossRunEntryIn] = Field(default_factory=list)
    requested_limit: float | None = Field(default=None, gt=0)
    requested_deductible: float | None = Field(default=None, ge=0)


class SubmissionOut(BaseModel):
    """Serialized underwriting submission with completeness, loss ratio, and risk brief."""

    id: str
    submission_number: str
    applicant_name: str
    broker_name: str
    line_of_business: str
    requested_effective_date: date
    requested_limit: float
    requested_deductible: float
    annual_revenue: float
    tiv_amount: float
    prior_premium: float
    loss_history: list[dict[str, Any]]
    documents_submitted: list[str]
    missing_documents: list[str]
    completeness_score: float
    total_incurred_losses: float
    loss_count: int
    loss_ratio_pct: float
    risk_score: float
    risk_tier: str
    risk_factors: list[dict[str, Any]]
    recommended_action: str
    indicated_premium: float
    status: str
    ai_risk_brief: str
    llm_provider_used: str
    approval_id: str | None
    created_at: datetime
    updated_at: datetime
