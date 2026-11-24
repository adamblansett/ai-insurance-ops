from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.config import Settings
from app.db.base import quantize_money

REQUIRED_DOCUMENTS_BY_LOB: dict[str, tuple[str, ...]] = {
    "commercial_property": (
        "acord_125",
        "acord_140",
        "statement_of_values",
        "loss_runs_5yr",
        "protective_safeguards",
    ),
    "commercial_general_liability": (
        "acord_125",
        "acord_126",
        "loss_runs_5yr",
        "financial_statements",
        "contract_indemnity_sample",
    ),
    "cyber": (
        "cyber_application",
        "mfa_attestation",
        "edr_backup_questionnaire",
        "loss_runs_3yr",
        "incident_response_plan",
    ),
    "commercial_auto": (
        "acord_125",
        "acord_127",
        "driver_schedule",
        "vehicle_schedule",
        "loss_runs_5yr",
    ),
}

_DEFAULT_REQUIRED_DOCS = (
    "acord_125",
    "supplemental_application",
    "loss_runs_5yr",
    "financial_statements",
)

_CRITICAL_DOCS = frozenset(
    {
        "protective_safeguards",
        "mfa_attestation",
        "edr_backup_questionnaire",
        "loss_runs_5yr",
        "loss_runs_3yr",
        "statement_of_values",
        "driver_schedule",
    }
)


@dataclass
class UnderwritingEvaluation:
    normalized_lob: str
    documents_submitted: list[str]
    missing_documents: list[str]
    completeness_score: float
    normalized_losses: list[dict[str, Any]]
    total_incurred_losses: Decimal
    loss_count: int
    loss_ratio_pct: float
    risk_score: float
    risk_tier: str
    risk_factors: list[dict[str, Any]]
    recommended_action: str
    indicated_premium: Decimal
    requires_hitl: bool
    status: str
    risk_level: str


def normalize_lob(raw_lob: str) -> str:
    cleaned = raw_lob.strip().lower().replace("-", "_").replace(" ", "_")
    if "cyber" in cleaned:
        return "cyber"
    if "general_liability" in cleaned or cleaned == "cgl":
        return "commercial_general_liability"
    if "auto" in cleaned:
        return "commercial_auto"
    if "property" in cleaned:
        return "commercial_property"
    return cleaned or "commercial_property"


def evaluate_submission(
    *,
    line_of_business: str,
    requested_limit: Decimal,
    requested_deductible: Decimal,
    tiv_amount: Decimal,
    prior_premium: Decimal,
    documents_submitted: list[str],
    loss_history: list[dict[str, Any]],
    settings: Settings,
) -> UnderwritingEvaluation:
    """Assess submission completeness, historical loss ratio, composite risk, and pricing."""
    lob = normalize_lob(line_of_business)
    required_docs = REQUIRED_DOCUMENTS_BY_LOB.get(lob, _DEFAULT_REQUIRED_DOCS)
    submitted_norm = sorted({doc.strip().lower() for doc in documents_submitted if doc.strip()})
    submitted_set = set(submitted_norm)

    missing = [doc for doc in required_docs if doc not in submitted_set]
    present_count = len(required_docs) - len(missing)
    completeness_score = round((present_count / max(len(required_docs), 1)) * 100.0, 1)

    normalized_losses: list[dict[str, Any]] = []
    total_incurred = Decimal("0.00")
    open_claims = 0
    severe_claims = 0

    for entry in loss_history:
        paid = quantize_money(entry.get("paid_amount", 0) or 0)
        reserve = quantize_money(entry.get("reserve_amount", 0) or 0)
        raw_inc = entry.get("incurred_amount")
        incurred = (
            quantize_money(raw_inc)
            if raw_inc is not None
            else quantize_money(paid + reserve)
        )
        status_val = str(entry.get("status", "closed")).strip().lower()
        if status_val in ("open", "reopened"):
            open_claims += 1
        if incurred >= Decimal("100000.00"):
            severe_claims += 1
        total_incurred += incurred
        normalized_losses.append(
            {
                "loss_date": str(entry.get("loss_date", "")),
                "claim_number": str(entry.get("claim_number", "")),
                "peril": str(entry.get("peril", "other")),
                "status": status_val,
                "paid_amount": float(paid),
                "reserve_amount": float(reserve),
                "incurred_amount": float(incurred),
                "description": str(entry.get("description", "")),
            }
        )

    total_incurred = quantize_money(total_incurred)
    loss_count = len(normalized_losses)
    lookback_years = 3 if lob == "cyber" else 5

    # Determine base annual premium benchmark for loss ratio & indication
    if prior_premium > Decimal("0.00"):
        base_annual_premium = quantize_money(prior_premium)
    elif tiv_amount > Decimal("0.00"):
        base_annual_premium = quantize_money(tiv_amount * Decimal("0.0045"))
    else:
        base_annual_premium = quantize_money(requested_limit * Decimal("0.012"))
    if base_annual_premium <= Decimal("0.00"):
        base_annual_premium = Decimal("15000.00")

    earned_lookback = base_annual_premium * Decimal(lookback_years)
    loss_ratio_pct = round(
        float((total_incurred / earned_lookback) * Decimal("100")) if earned_lookback > 0 else 0.0,
        2,
    )

    risk_score = 12.0  # Baseline operational risk
    risk_factors: list[dict[str, Any]] = []

    if loss_ratio_pct > 65.0:
        risk_score += 38.0
        risk_factors.append(
            {
                "code": "HIGH_LOSS_RATIO",
                "severity": "critical",
                "factor": (
                    f"{lookback_years}-year loss ratio of {loss_ratio_pct:.1f}% "
                    "exceeds 65% threshold."
                ),
                "mitigation": (
                    "Apply >=35% rate surcharge or increase retention; escalate to senior UW."
                ),
            }
        )
    elif loss_ratio_pct > 45.0:
        risk_score += 20.0
        risk_factors.append(
            {
                "code": "ELEVATED_LOSS_RATIO",
                "severity": "medium",
                "factor": (
                    f"{lookback_years}-year loss ratio of {loss_ratio_pct:.1f}% "
                    "is above 45% target."
                ),
                "mitigation": "Apply 15-25% technical rate adjustment and loss-control conditions.",
            }
        )

    if loss_count >= 4:
        risk_score += 20.0
        risk_factors.append(
            {
                "code": "LOSS_FREQUENCY",
                "severity": "high",
                "factor": f"{loss_count} claims reported in the {lookback_years}-year lookback.",
                "mitigation": (
                    "Require quarterly risk-engineering inspections and higher deductible."
                ),
            }
        )
    elif loss_count == 3:
        risk_score += 12.0
        risk_factors.append(
            {
                "code": "MODERATE_FREQUENCY",
                "severity": "medium",
                "factor": f"3 claims recorded during {lookback_years}-year loss history.",
                "mitigation": "Review root-cause corrective actions prior to binding.",
            }
        )

    if open_claims > 0 or severe_claims > 0:
        risk_score += 15.0 if severe_claims > 0 else 8.0
        risk_factors.append(
            {
                "code": "OPEN_OR_SEVERE_CLAIMS",
                "severity": "high" if severe_claims > 0 else "medium",
                "factor": (
                    f"{open_claims} open claim(s) and {severe_claims} "
                    "severe loss(es) >= $100k."
                ),
                "mitigation": "Obtain updated adjuster reserve memos and subrogation status.",
            }
        )

    missing_critical = [doc for doc in missing if doc in _CRITICAL_DOCS]
    if missing:
        doc_penalty = min(28.0, len(missing) * 5.0 + len(missing_critical) * 6.0)
        risk_score += doc_penalty
        risk_factors.append(
            {
                "code": "INCOMPLETE_SUBMISSION",
                "severity": "high" if missing_critical else "medium",
                "factor": f"Missing {len(missing)} required document(s): {', '.join(missing)}.",
                "mitigation": (
                    "Subjectivity required before bind: collect all missing underwriting docs."
                ),
            }
        )

    if requested_limit > Decimal("0.00") and (
        requested_deductible < requested_limit * Decimal("0.005")
    ):
        risk_score += 8.0
        risk_factors.append(
            {
                "code": "THIN_DEDUCTIBLE_RATIO",
                "severity": "low",
                "factor": (
                    f"Requested deductible ${requested_deductible:,.2f} is below 0.5% "
                    f"of limit ${requested_limit:,.2f}."
                ),
                "mitigation": "Propose minimum deductible equal to 0.5%-1.0% of occurrence limit.",
            }
        )

    bounded_score = round(min(100.0, max(0.0, risk_score)), 1)

    if bounded_score < 30.0:
        risk_tier = "preferred"
        recommended_action = "quote"
        rate_factor = Decimal("0.95")
    elif bounded_score < 55.0:
        risk_tier = "standard"
        recommended_action = "quote_with_conditions"
        rate_factor = Decimal("1.08")
    elif bounded_score < 75.0:
        risk_tier = "substandard"
        recommended_action = "refer_senior_uw"
        rate_factor = Decimal("1.28")
    else:
        risk_tier = "decline_recommended"
        recommended_action = "decline"
        rate_factor = Decimal("1.55")

    indicated_premium = quantize_money(base_annual_premium * rate_factor)

    requires_hitl = (
        recommended_action != "quote"
        or requested_limit >= Decimal(str(settings.uw_auto_quote_limit))
    )
    status_val = "pending_uw_approval" if requires_hitl else "quoted_ready"
    risk_level = (
        "critical"
        if risk_tier == "decline_recommended"
        else ("high" if risk_tier == "substandard" else "medium" if requires_hitl else "low")
    )

    return UnderwritingEvaluation(
        normalized_lob=lob,
        documents_submitted=submitted_norm,
        missing_documents=missing,
        completeness_score=completeness_score,
        normalized_losses=normalized_losses,
        total_incurred_losses=total_incurred,
        loss_count=loss_count,
        loss_ratio_pct=loss_ratio_pct,
        risk_score=bounded_score,
        risk_tier=risk_tier,
        risk_factors=risk_factors,
        recommended_action=recommended_action,
        indicated_premium=indicated_premium,
        requires_hitl=requires_hitl,
        status=status_val,
        risk_level=risk_level,
    )
