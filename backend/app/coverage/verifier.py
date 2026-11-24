import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.config import Settings
from app.db.base import quantize_money
from app.db.models import Claim, Policy, PolicyClause
from app.intake.embeddings import cosine_similarity, embed_text, tokenize

_PERIL_TERMS: dict[str, set[str]] = {
    "water_damage": {
        "water",
        "pipe",
        "pipes",
        "burst",
        "plumbing",
        "backup",
        "sewer",
        "drain",
        "sump",
        "overflow",
        "sprinkler",
        "discharge",
        "leakage",
    },
    "flood": {
        "flood",
        "surface",
        "surge",
        "coastal",
        "tidal",
        "overflow",
        "inundation",
        "waves",
    },
    "fire": {"fire", "smoke", "lightning", "explosion", "combustion", "burn"},
    "wind_hail": {"wind", "windstorm", "hail", "roof", "tornado", "hurricane", "storm"},
    "theft": {"theft", "burglary", "robbery", "stolen", "larceny", "break"},
    "bodily_injury": {"bodily", "injury", "medical", "premises", "liability", "slip", "fall"},
    "auto_collision": {"auto", "vehicle", "collision", "crash", "fleet", "driver"},
    "cyber_ransomware": {
        "cyber",
        "ransomware",
        "extortion",
        "network",
        "encryption",
        "breach",
        "malware",
        "data",
        "restoration",
        "security",
    },
    "other": set(),
}

# Sub-topics used to check whether an endorsement specifically buys back a matching exclusion
_SPECIFIC_EXCLUSION_TOPICS: dict[str, set[str]] = {
    "water_backup": {"backup", "sewer", "drain", "sump"},
    "flood": {"flood", "tidal", "surge", "coastal", "tsunami"},
    "ransomware": {"ransomware", "extortion", "cyber", "encryption", "malware"},
    "wind_hail": {"windstorm", "hail", "wind"},
    "theft": {"theft", "burglary", "robbery"},
}


@dataclass
class CoverageEvaluation:
    determination: str
    policy_in_force: bool
    applicable_limit: Decimal
    applicable_deductible: Decimal
    estimated_covered_payout: Decimal
    excess_over_limit: Decimal
    matched_clauses: list[dict[str, Any]]
    triggered_exclusions: list[dict[str, Any]]
    citations: list[str]
    confidence_score: float
    requires_hitl_review: bool
    status: str
    summary_rationale: str


def format_clause_citation(policy_number: str, clause: PolicyClause) -> str:
    """Format a deterministic Page + Section citation string."""
    return f"{policy_number} · Page {clause.page_number} · {clause.section_ref} — {clause.title}"


def _clause_topics(text: str) -> set[str]:
    tokens = set(tokenize(text))
    topics: set[str] = set()
    for topic, kw in _SPECIFIC_EXCLUSION_TOPICS.items():
        if tokens & kw:
            topics.add(topic)
    return topics


def _score_clause(
    *,
    claim_tokens: set[str],
    claim_vec: list[float],
    peril_tokens: set[str],
    clause: PolicyClause,
) -> tuple[float, set[str]]:
    clause_text_all = f"{clause.title} {clause.clause_text}"
    clause_tokens = set(clause.keywords_json) | set(tokenize(clause_text_all))
    shared_claim = claim_tokens & clause_tokens
    shared_peril = peril_tokens & clause_tokens

    sim = cosine_similarity(claim_vec, clause.embedding_json)
    claim_overlap = len(shared_claim) / max(len(claim_tokens), 1) if claim_tokens else 0.0
    peril_overlap = len(shared_peril) / max(min(len(peril_tokens), 4), 1) if peril_tokens else 0.0
    score = round(min(1.0, max(0.0, sim * 0.40 + claim_overlap * 0.30 + peril_overlap * 0.45)), 4)
    return score, shared_claim | shared_peril


def _exclusion_applies(
    *,
    claim_peril: str,
    claim_tokens: set[str],
    clause: PolicyClause,
    score: float,
    shared_terms: set[str],
) -> bool:
    """Determine whether an exclusion clause truly applies to the claim facts."""
    clause_tokens = set(tokenize(f"{clause.title} {clause.clause_text}"))

    # Never trigger a flood/surface-water exclusion purely on generic "water" for pipe burst
    if (
        "flood" in clause_tokens
        and claim_peril != "flood"
        and not (claim_tokens & {"flood", "surge", "tidal", "coastal", "surface"})
    ):
        return False

    # Never trigger a sewer/backup exclusion unless backup/sewer/drain/sump is in the claim facts
    if (clause_tokens & {"sewer", "backup", "sump"}) and not (
        claim_tokens & {"sewer", "backup", "sump", "drain"}
    ):
        return False

    if len(shared_terms) >= 2:
        return True
    if len(shared_terms) == 1 and score >= 0.38:
        # Check the single matched word is a substantive peril keyword
        substantive = shared_terms - {"property", "damage", "loss", "claim", "coverage", "water"}
        return bool(substantive)
    return False


def _endorsement_overrides_exclusion(
    exclusion: PolicyClause,
    endorsements: list[PolicyClause],
    claim_tokens: set[str],
) -> PolicyClause | None:
    """Return a matching endorsement/sublimit that explicitly buys back an exclusion."""
    excl_topics = _clause_topics(f"{exclusion.title} {exclusion.clause_text}")
    excl_tokens = set(tokenize(f"{exclusion.title} {exclusion.clause_text}"))

    for end in endorsements:
        end_full = f"{end.title} {end.clause_text}"
        end_lower = end_full.lower()
        end_tokens = set(tokenize(end_full))
        end_topics = _clause_topics(end_full)

        # Must share an explicit buy-back topic (e.g., water_backup) and claim relevance
        topic_match = bool(excl_topics & end_topics)
        token_overlap = len((excl_tokens & end_tokens) & claim_tokens) >= 1
        buyback_language = (
            "endorsement" in end.clause_type
            or "sublimit" in end.clause_type
            or "buy-back" in end_lower
            or "extends coverage" in end_lower
            or "overrides" in end_lower
            or "notwithstanding" in end_lower
        )
        if buyback_language and (topic_match or (token_overlap and end.monetary_limit is not None)):
            return end
    return None


def _check_condition_breach(
    claim: Claim,
    conditions: list[PolicyClause],
) -> tuple[PolicyClause | None, str]:
    """Detect notice or cooperation condition breaches cited in policy conditions."""
    reporting_delay_days = (claim.reported_date - claim.loss_date).days
    for cond in conditions:
        full_lower = f"{cond.title} {cond.clause_text}".lower()
        is_notice = "notice" in full_lower or "notify" in full_lower or "report" in full_lower
        hour_match = re.search(r"(\d+)\s*hours?", full_lower)
        if hour_match and is_notice:
            limit_hours = int(hour_match.group(1))
            if reporting_delay_days * 24 > limit_hours:
                return (
                    cond,
                    f"Claim reported {reporting_delay_days} days ({reporting_delay_days * 24}h) "
                    f"after loss, exceeding {limit_hours}h notice condition.",
                )
        day_match = re.search(r"(\d+)\s*days?", full_lower)
        if day_match and is_notice:
            limit_days = int(day_match.group(1))
            if reporting_delay_days > limit_days:
                return (
                    cond,
                    f"Claim reported {reporting_delay_days} days after loss, "
                    f"exceeding {limit_days}-day notice condition.",
                )
    return None, ""


def evaluate_coverage(
    *,
    claim: Claim,
    policy: Policy,
    clauses: list[PolicyClause],
    settings: Settings,
) -> CoverageEvaluation:
    """Evaluate claim facts against indexed policy clauses with exact Decimal math & citations."""
    in_force = (
        policy.status == "active"
        and policy.effective_date <= claim.loss_date <= policy.expiration_date
    )

    if not in_force:
        reason = (
            f"Policy {policy.policy_number} status is '{policy.status}' "
            f"(effective {policy.effective_date} to {policy.expiration_date}), "
            f"not in force on loss date {claim.loss_date}."
        )
        citation = f"{policy.policy_number} · Page 1 · Declarations — Policy Term & Status"
        return CoverageEvaluation(
            determination="policy_inactive",
            policy_in_force=False,
            applicable_limit=Decimal("0.00"),
            applicable_deductible=quantize_money(policy.deductible),
            estimated_covered_payout=Decimal("0.00"),
            excess_over_limit=Decimal("0.00"),
            matched_clauses=[],
            triggered_exclusions=[
                {
                    "clause_id": None,
                    "section_ref": "Declarations",
                    "page_number": 1,
                    "title": "Policy Effective Period / Active Status",
                    "overridden_by": None,
                    "citation": citation,
                }
            ],
            citations=[citation],
            confidence_score=0.97,
            requires_hitl_review=True,
            status="pending_review",
            summary_rationale=reason,
        )

    claim_text = f"{claim.peril_type.replace('_', ' ')} {claim.loss_description}"
    claim_tokens = set(tokenize(claim_text))
    peril_tokens = _PERIL_TERMS.get(claim.peril_type, set()) | set(
        tokenize(claim.peril_type.replace("_", " "))
    )
    claim_vec = embed_text(claim_text, dims=settings.embedding_dimensions)

    scored_clauses: list[tuple[PolicyClause, float, set[str]]] = []
    for clause in clauses:
        sc, shared = _score_clause(
            claim_tokens=claim_tokens,
            claim_vec=claim_vec,
            peril_tokens=peril_tokens,
            clause=clause,
        )
        scored_clauses.append((clause, sc, shared))

    scored_clauses.sort(key=lambda item: (-item[1], item[0].page_number))

    grants_and_endorsements = [
        (c, sc, sh)
        for c, sc, sh in scored_clauses
        if c.clause_type in ("coverage_grant", "endorsement", "sublimit") and sc >= 0.12
    ]
    endorsements_only = [
        c
        for c, sc, _ in scored_clauses
        if c.clause_type in ("endorsement", "sublimit") and sc >= 0.18
    ]
    exclusions = [(c, sc, sh) for c, sc, sh in scored_clauses if c.clause_type == "exclusion"]
    conditions = [c for c, _, _ in scored_clauses if c.clause_type == "condition"]

    triggered_exclusions: list[dict[str, Any]] = []
    active_exclusions: list[PolicyClause] = []
    overriding_endorsements: list[PolicyClause] = []
    citations: list[str] = []

    for excl, sc, shared in exclusions:
        if _exclusion_applies(
            claim_peril=claim.peril_type,
            claim_tokens=claim_tokens,
            clause=excl,
            score=sc,
            shared_terms=shared,
        ):
            override = _endorsement_overrides_exclusion(excl, endorsements_only, claim_tokens)
            excl_cite = format_clause_citation(policy.policy_number, excl)
            citations.append(excl_cite)
            if override is not None:
                overriding_endorsements.append(override)
                over_cite = format_clause_citation(policy.policy_number, override)
                citations.append(over_cite)
                triggered_exclusions.append(
                    {
                        "clause_id": excl.id,
                        "section_ref": excl.section_ref,
                        "page_number": excl.page_number,
                        "title": excl.title,
                        "overridden_by": f"{override.section_ref} — {override.title}",
                        "citation": excl_cite,
                    }
                )
            else:
                active_exclusions.append(excl)
                triggered_exclusions.append(
                    {
                        "clause_id": excl.id,
                        "section_ref": excl.section_ref,
                        "page_number": excl.page_number,
                        "title": excl.title,
                        "overridden_by": None,
                        "citation": excl_cite,
                    }
                )

    matched_clauses: list[dict[str, Any]] = []
    for clause, sc, _ in grants_and_endorsements[:4]:
        cite = format_clause_citation(policy.policy_number, clause)
        if cite not in citations:
            citations.append(cite)
        matched_clauses.append(
            {
                "clause_id": clause.id,
                "clause_type": clause.clause_type,
                "section_ref": clause.section_ref,
                "page_number": clause.page_number,
                "title": clause.title,
                "score": sc,
                "monetary_limit": (
                    float(clause.monetary_limit) if clause.monetary_limit is not None else None
                ),
                "deductible_override": (
                    float(clause.deductible_override)
                    if clause.deductible_override is not None
                    else None
                ),
                "citation": cite,
            }
        )

    # Determine applicable limit & deductible from overriding endorsement or primary matching grant
    primary_grants = [c for c, _, _ in grants_and_endorsements if c.clause_type == "coverage_grant"]
    if overriding_endorsements:
        governing_clauses = overriding_endorsements
    elif primary_grants:
        governing_clauses = [primary_grants[0]]
    else:
        governing_clauses = [c for c, _, _ in grants_and_endorsements[:1]]
    applicable_limit = quantize_money(policy.per_occurrence_limit)
    applicable_deductible = quantize_money(policy.deductible)

    sublimits = [
        quantize_money(c.monetary_limit)
        for c in governing_clauses
        if c.monetary_limit is not None and c.monetary_limit > Decimal("0.00")
    ]
    if sublimits:
        applicable_limit = min(applicable_limit, min(sublimits))

    ded_overrides = [
        quantize_money(c.deductible_override)
        for c in governing_clauses
        if c.deductible_override is not None
    ]
    if ded_overrides:
        applicable_deductible = ded_overrides[0]

    condition_breach, condition_reason = _check_condition_breach(claim, conditions)
    if condition_breach is not None:
        cond_cite = format_clause_citation(policy.policy_number, condition_breach)
        if cond_cite not in citations:
            citations.append(cond_cite)

    claimed_dec = quantize_money(claim.claimed_amount)
    net_after_deductible = max(
        Decimal("0.00"), quantize_money(claimed_dec - applicable_deductible)
    )
    estimated_payout = min(net_after_deductible, applicable_limit)
    excess_over_limit = max(
        Decimal("0.00"), quantize_money(net_after_deductible - applicable_limit)
    )

    if active_exclusions:
        determination = "excluded"
        estimated_payout = Decimal("0.00")
        excess_over_limit = Decimal("0.00")
        rationale = (
            f"Exclusion triggered: {active_exclusions[0].section_ref} "
            f"(Page {active_exclusions[0].page_number}) — {active_exclusions[0].title}."
        )
    elif condition_breach is not None or claim.fraud_score >= settings.fraud_siu_threshold:
        determination = "reservation_of_rights"
        reasons = []
        if condition_breach is not None:
            reasons.append(condition_reason)
        if claim.fraud_score >= settings.fraud_siu_threshold:
            reasons.append(
                f"SIU fraud score {claim.fraud_score:.2f} >= "
                f"threshold {settings.fraud_siu_threshold:.2f}."
            )
        rationale = "Reservation of Rights issued: " + " ".join(reasons)
    elif excess_over_limit > Decimal("0.00") or overriding_endorsements:
        determination = "partial_coverage" if excess_over_limit > Decimal("0.00") else "covered"
        if overriding_endorsements:
            rationale = (
                f"Coverage extended via {overriding_endorsements[0].section_ref} "
                f"(Page {overriding_endorsements[0].page_number}) with limit "
                f"${applicable_limit:,.2f} and deductible ${applicable_deductible:,.2f}."
            )
        else:
            rationale = (
                f"Claimed amount exceeds applicable limit ${applicable_limit:,.2f} "
                f"by ${excess_over_limit:,.2f} after ${applicable_deductible:,.2f} deductible."
            )
    else:
        determination = "covered"
        rationale = (
            f"Covered under {policy.policy_number} with ${applicable_limit:,.2f} limit "
            f"and ${applicable_deductible:,.2f} deductible; net estimated payout "
            f"${estimated_payout:,.2f}."
        )

    if not citations:
        citations.append(f"{policy.policy_number} · Page 1 · Declarations — Insuring Agreement")

    requires_hitl = determination in (
        "excluded",
        "reservation_of_rights",
        "policy_inactive",
    ) or estimated_payout >= Decimal(str(settings.coverage_auto_approve_limit))
    status_val = "pending_review" if requires_hitl else "auto_verified"

    top_score = grants_and_endorsements[0][1] if grants_and_endorsements else 0.65
    confidence = round(min(0.98, max(0.68, 0.60 + top_score * 0.35)), 2)

    return CoverageEvaluation(
        determination=determination,
        policy_in_force=True,
        applicable_limit=applicable_limit,
        applicable_deductible=applicable_deductible,
        estimated_covered_payout=quantize_money(estimated_payout),
        excess_over_limit=quantize_money(excess_over_limit),
        matched_clauses=matched_clauses,
        triggered_exclusions=triggered_exclusions,
        citations=citations,
        confidence_score=confidence,
        requires_hitl_review=requires_hitl,
        status=status_val,
        summary_rationale=rationale,
    )
