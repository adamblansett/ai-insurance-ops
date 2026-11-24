import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.core.config import Settings
from app.db.base import quantize_money
from app.db.models import Claim, Policy

_PERIL_ALIASES: dict[str, str] = {
    "water": "water_damage",
    "water_damage": "water_damage",
    "pipe_burst": "water_damage",
    "sprinkler": "water_damage",
    "sewer_backup": "water_damage",
    "fire": "fire",
    "smoke": "fire",
    "wind": "wind_hail",
    "hail": "wind_hail",
    "wind_hail": "wind_hail",
    "theft": "theft",
    "burglary": "theft",
    "robbery": "theft",
    "bodily_injury": "bodily_injury",
    "injury": "bodily_injury",
    "slip_fall": "bodily_injury",
    "auto": "auto_collision",
    "auto_collision": "auto_collision",
    "collision": "auto_collision",
    "cyber": "cyber_ransomware",
    "ransomware": "cyber_ransomware",
    "cyber_ransomware": "cyber_ransomware",
    "data_breach": "cyber_ransomware",
    "flood": "flood",
    "storm_surge": "flood",
}

_SUSPICIOUS_CUE_RE = re.compile(
    r"(?i)\b(cash\s+only|prior\s+damage|inconsistent|refused\s+inspection|pre-existing|staged)\b"
)


@dataclass
class TriageDecision:
    normalized_peril: str
    severity_tier: str
    reserve_band: str
    recommended_reserve: Decimal
    adjuster_queue: str
    fraud_score: float
    fraud_indicators: list[dict[str, Any]]
    triage_status: str
    requires_hitl: bool
    approval_entity_type: str | None
    approval_action: str | None
    risk_level: str


def normalize_peril(raw_peril: str, description: str = "") -> str:
    """Map free-form or enumerated peril labels into canonical peril types."""
    cleaned = raw_peril.strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in _PERIL_ALIASES:
        return _PERIL_ALIASES[cleaned]
    desc_lower = description.lower()
    if any(w in desc_lower for w in ("ransomware", "malware", "encryption", "phishing")):
        return "cyber_ransomware"
    if any(
        w in desc_lower
        for w in ("storm surge", "coastal flood", "rising tide", "river overflow")
    ):
        return "flood"
    if any(w in desc_lower for w in ("pipe", "water", "sprinkler", "leak", "sump")):
        return "water_damage"
    if any(w in desc_lower for w in ("fire", "arson", "smoke")):
        return "fire"
    if any(w in desc_lower for w in ("theft", "stolen", "burglary")):
        return "theft"
    if any(w in desc_lower for w in ("hail", "windstorm", "tornado")):
        return "wind_hail"
    if any(w in desc_lower for w in ("injury", "hospital", "fracture", "slip and fall")):
        return "bodily_injury"
    if any(w in desc_lower for w in ("collision", "rear-ended", "vehicle")):
        return "auto_collision"
    return "other"


def _compute_reserve_band(amount: Decimal) -> str:
    if amount < Decimal("10000"):
        return "fast_track_0_10k"
    if amount < Decimal("50000"):
        return "standard_10k_50k"
    if amount < Decimal("250000"):
        return "complex_50k_250k"
    return "executive_250k_plus"


def evaluate_fnol_triage(
    *,
    claim_number: str,
    loss_date: date,
    reported_date: date,
    peril_type: str,
    loss_description: str,
    claimed_amount: Decimal,
    injuries_reported: bool,
    police_report_filed: bool,
    policy: Policy | None,
    existing_claims: list[Claim],
    settings: Settings,
) -> TriageDecision:
    """Score FNOL severity, reserve band, fraud red flags, and adjuster routing."""
    norm_peril = normalize_peril(peril_type, loss_description)

    reserve_multiplier = Decimal("1.15") if (
        injuries_reported or norm_peril in ("fire", "cyber_ransomware", "bodily_injury")
    ) else Decimal("1.00")
    recommended_reserve = quantize_money(claimed_amount * reserve_multiplier)
    if policy is not None and policy.per_occurrence_limit > Decimal("0.00"):
        recommended_reserve = min(recommended_reserve, quantize_money(policy.per_occurrence_limit))

    reserve_band = _compute_reserve_band(recommended_reserve)

    if recommended_reserve >= Decimal("250000") or (
        injuries_reported and recommended_reserve >= Decimal("100000")
    ):
        severity_tier = "catastrophic"
    elif (
        recommended_reserve >= Decimal("50000")
        or injuries_reported
        or norm_peril in ("fire", "cyber_ransomware")
    ):
        severity_tier = "high"
    elif recommended_reserve >= Decimal("10000"):
        severity_tier = "medium"
    else:
        severity_tier = "low"

    indicators: list[dict[str, Any]] = []
    score = 0.0

    def _add_indicator(code: str, severity: str, weight: float, message: str) -> None:
        nonlocal score
        indicators.append(
            {
                "code": code,
                "severity": severity,
                "weight": weight,
                "message": message,
            }
        )
        score += weight

    if policy is None:
        _add_indicator(
            "POLICY_NOT_FOUND",
            "medium",
            0.25,
            "Reported policy number did not match an ingested active declaration.",
        )
    else:
        if loss_date < policy.effective_date or loss_date > policy.expiration_date:
            _add_indicator(
                "OUTSIDE_POLICY_PERIOD",
                "high",
                0.45,
                (
                    f"Loss date {loss_date} falls outside policy term "
                    f"({policy.effective_date} to {policy.expiration_date})."
                ),
            )
        elif (loss_date - policy.effective_date).days <= 30:
            _add_indicator(
                "EARLY_POLICY_LOSS",
                "high",
                0.35,
                (
                    f"Loss occurred {(loss_date - policy.effective_date).days} days "
                    "after policy inception (<= 30-day inception window)."
                ),
            )
        if policy.per_occurrence_limit > Decimal("0.00") and (
            claimed_amount >= policy.per_occurrence_limit * Decimal("0.90")
        ):
            _add_indicator(
                "NEAR_LIMIT_CLAIM",
                "medium",
                0.20,
                "Claimed amount is >= 90% of the policy per-occurrence limit.",
            )

    reporting_delay = (reported_date - loss_date).days
    if reporting_delay > 30:
        _add_indicator(
            "LATE_REPORTING",
            "medium",
            0.20,
            f"FNOL reported {reporting_delay} days after loss date (> 30-day threshold).",
        )

    if norm_peril == "theft" and not police_report_filed:
        _add_indicator(
            "NO_POLICE_REPORT_THEFT",
            "medium",
            0.25,
            "Theft claim submitted without an accompanying police report.",
        )

    cue_hits = _SUSPICIOUS_CUE_RE.findall(loss_description)
    if cue_hits:
        unique_cues = ", ".join(sorted({c.lower() for c in cue_hits}))
        _add_indicator(
            "SUSPICIOUS_NARRATIVE_CUES",
            "high",
            0.30,
            f"Narrative contains SIU trigger phrases: {unique_cues}.",
        )

    for prior in existing_claims:
        if prior.claim_number == claim_number:
            continue
        same_policy = (
            policy is not None and prior.policy_id == policy.id
        ) or prior.policy_number_reported == (policy.policy_number if policy else "")
        if (
            same_policy
            and prior.peril_type == norm_peril
            and abs((prior.loss_date - loss_date).days) <= 7
        ):
            _add_indicator(
                "DUPLICATE_LOSS_PATTERN",
                "high",
                0.40,
                (
                    f"Matches prior claim {prior.claim_number} ({prior.peril_type}) "
                    f"within 7 days of {prior.loss_date}."
                ),
            )
            break

    fraud_score = round(min(1.0, max(0.0, score)), 2)

    if fraud_score >= settings.fraud_siu_threshold:
        adjuster_queue = "siu_investigation"
    elif norm_peril == "cyber_ransomware":
        adjuster_queue = "cyber_incident"
    elif injuries_reported or (
        severity_tier in ("high", "catastrophic") and norm_peril == "bodily_injury"
    ):
        adjuster_queue = "complex_casualty"
    elif reserve_band == "fast_track_0_10k" and fraud_score < 0.30:
        adjuster_queue = "fast_track_desk"
    else:
        adjuster_queue = "field_property"

    requires_hitl = False
    approval_entity_type: str | None = None
    approval_action: str | None = None
    triage_status = "triaged"
    risk_level = "low"

    if fraud_score >= settings.fraud_siu_threshold:
        requires_hitl = True
        approval_entity_type = "siu_referral"
        approval_action = "approve_siu_referral"
        triage_status = "pending_siu_review"
        risk_level = "critical" if fraud_score >= 0.80 else "high"
    elif recommended_reserve >= Decimal(str(settings.reserve_auto_approve_limit)):
        requires_hitl = True
        approval_entity_type = "claim_reserve"
        approval_action = "approve_reserve_authority"
        triage_status = "pending_reserve_approval"
        risk_level = "high" if recommended_reserve >= Decimal("100000") else "medium"

    return TriageDecision(
        normalized_peril=norm_peril,
        severity_tier=severity_tier,
        reserve_band=reserve_band,
        recommended_reserve=recommended_reserve,
        adjuster_queue=adjuster_queue,
        fraud_score=fraud_score,
        fraud_indicators=indicators,
        triage_status=triage_status,
        requires_hitl=requires_hitl,
        approval_entity_type=approval_entity_type,
        approval_action=approval_action,
        risk_level=risk_level,
    )
