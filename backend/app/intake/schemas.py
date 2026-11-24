from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ClauseType = Literal[
    "coverage_grant",
    "exclusion",
    "endorsement",
    "condition",
    "sublimit",
    "definition",
]


class PolicyClauseIn(BaseModel):
    """Input schema for indexing an individual policy clause or endorsement."""

    clause_type: ClauseType = "coverage_grant"
    section_ref: str = Field(default="Section I", max_length=120)
    page_number: int = Field(default=1, ge=1)
    title: str = Field(min_length=2, max_length=240)
    clause_text: str = Field(min_length=3)
    monetary_limit: float | None = Field(default=None, ge=0)
    deductible_override: float | None = Field(default=None, ge=0)
    keywords: list[str] = Field(default_factory=list)


class PolicyCreateIn(BaseModel):
    """Structured policy intake payload."""

    policy_number: str = Field(min_length=3, max_length=120)
    carrier_name: str = Field(default="ShieldGuard Commercial Insurance Co.", max_length=200)
    named_insured: str = Field(min_length=2, max_length=240)
    insured_address: str = Field(default="", max_length=320)
    line_of_business: str = Field(default="commercial_property", max_length=80)
    acord_form_type: str = Field(default="ACORD 140", max_length=80)
    effective_date: date
    expiration_date: date
    status: Literal["active", "expired", "cancelled", "pending_bind"] = "active"
    per_occurrence_limit: float = Field(gt=0)
    aggregate_limit: float = Field(gt=0)
    deductible: float = Field(default=0.0, ge=0)
    annual_premium: float = Field(default=0.0, ge=0)
    schedules: list[dict[str, Any]] = Field(default_factory=list)
    clauses: list[PolicyClauseIn] = Field(default_factory=list)


class PolicyClauseOut(BaseModel):
    """Serialized policy clause with page and section metadata."""

    id: str
    policy_id: str
    clause_type: str
    section_ref: str
    page_number: int
    title: str
    clause_text: str
    monetary_limit: float | None
    deductible_override: float | None
    keywords: list[str]


class PolicySummaryOut(BaseModel):
    """Summary policy card returned by policy listing endpoints."""

    id: str
    policy_number: str
    carrier_name: str
    named_insured: str
    insured_address: str
    line_of_business: str
    acord_form_type: str
    effective_date: date
    expiration_date: date
    status: str
    per_occurrence_limit: float
    aggregate_limit: float
    deductible: float
    annual_premium: float
    source_filename: str
    extraction_confidence: float
    clause_count: int
    ai_summary: str
    created_at: datetime


class PolicyDetailOut(PolicySummaryOut):
    """Detailed policy response including schedules and indexed clauses."""

    extracted_schedules: list[dict[str, Any]]
    clauses: list[PolicyClauseOut]


class ClauseSearchIn(BaseModel):
    """Query payload for hybrid semantic + keyword clause search."""

    query: str = Field(min_length=2, max_length=500)
    policy_id: str | None = None
    clause_type: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class ClauseSearchResultOut(BaseModel):
    """Ranked clause match with score and human-auditable citation."""

    clause_id: str
    policy_id: str
    policy_number: str
    named_insured: str
    clause_type: str
    section_ref: str
    page_number: int
    title: str
    clause_text: str
    monetary_limit: float | None
    deductible_override: float | None
    score: float
    citation: str
