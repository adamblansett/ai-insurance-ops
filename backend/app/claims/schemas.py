from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PerilType = Literal[
    "water_damage",
    "fire",
    "wind_hail",
    "theft",
    "bodily_injury",
    "auto_collision",
    "cyber_ransomware",
    "flood",
    "other",
]


class ClaimCreateIn(BaseModel):
    """FNOL intake submission payload."""

    claim_number: str = Field(min_length=3, max_length=120)
    policy_number_reported: str = Field(min_length=2, max_length=120)
    claimant_name: str = Field(min_length=2, max_length=240)
    loss_date: date
    reported_date: date
    loss_location: str = Field(default="", max_length=240)
    peril_type: str = Field(default="other", max_length=64)
    loss_description: str = Field(min_length=5, max_length=5000)
    claimed_amount: float = Field(gt=0)
    injuries_reported: bool = False
    police_report_filed: bool = False


class FraudIndicatorOut(BaseModel):
    """Structured fraud risk indicator detected during FNOL triage."""

    code: str
    severity: str
    weight: float
    message: str


class ClaimOut(BaseModel):
    """Serialized claim record with triage scoring and routing metadata."""

    id: str
    claim_number: str
    policy_id: str | None
    policy_number_reported: str
    claimant_name: str
    loss_date: date
    reported_date: date
    loss_location: str
    peril_type: str
    loss_description: str
    claimed_amount: float
    injuries_reported: bool
    police_report_filed: bool
    severity_tier: str
    reserve_band: str
    recommended_reserve: float
    adjuster_queue: str
    fraud_score: float
    fraud_indicators: list[dict[str, Any]]
    triage_status: str
    ai_triage_summary: str
    llm_provider_used: str
    approval_id: str | None
    created_at: datetime
    updated_at: datetime
