import hashlib

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.core.auth import Actor
from app.core.config import Settings
from app.db.base import quantize_money
from app.db.models import Policy, PolicyClause
from app.intake.embeddings import cosine_similarity, embed_text, extract_keywords, tokenize
from app.intake.parser import extract_pages_from_bytes, parse_policy_document
from app.intake.schemas import (
    ClauseSearchResultOut,
    PolicyClauseOut,
    PolicyCreateIn,
    PolicyDetailOut,
    PolicySummaryOut,
)
from app.llm.router import LLMRouter


def serialize_clause(clause: PolicyClause) -> PolicyClauseOut:
    return PolicyClauseOut(
        id=clause.id,
        policy_id=clause.policy_id,
        clause_type=clause.clause_type,
        section_ref=clause.section_ref,
        page_number=clause.page_number,
        title=clause.title,
        clause_text=clause.clause_text,
        monetary_limit=float(clause.monetary_limit) if clause.monetary_limit is not None else None,
        deductible_override=(
            float(clause.deductible_override) if clause.deductible_override is not None else None
        ),
        keywords=clause.keywords_json,
    )


def serialize_policy_summary(policy: Policy, clause_count: int) -> PolicySummaryOut:
    return PolicySummaryOut(
        id=policy.id,
        policy_number=policy.policy_number,
        carrier_name=policy.carrier_name,
        named_insured=policy.named_insured,
        insured_address=policy.insured_address,
        line_of_business=policy.line_of_business,
        acord_form_type=policy.acord_form_type,
        effective_date=policy.effective_date,
        expiration_date=policy.expiration_date,
        status=policy.status,
        per_occurrence_limit=float(policy.per_occurrence_limit),
        aggregate_limit=float(policy.aggregate_limit),
        deductible=float(policy.deductible),
        annual_premium=float(policy.annual_premium),
        source_filename=policy.source_filename,
        extraction_confidence=policy.extraction_confidence,
        clause_count=clause_count,
        ai_summary=policy.ai_summary,
        created_at=policy.created_at,
    )


def serialize_policy_detail(policy: Policy) -> PolicyDetailOut:
    clauses = [serialize_clause(c) for c in policy.clauses]
    return PolicyDetailOut(
        id=policy.id,
        policy_number=policy.policy_number,
        carrier_name=policy.carrier_name,
        named_insured=policy.named_insured,
        insured_address=policy.insured_address,
        line_of_business=policy.line_of_business,
        acord_form_type=policy.acord_form_type,
        effective_date=policy.effective_date,
        expiration_date=policy.expiration_date,
        status=policy.status,
        per_occurrence_limit=float(policy.per_occurrence_limit),
        aggregate_limit=float(policy.aggregate_limit),
        deductible=float(policy.deductible),
        annual_premium=float(policy.annual_premium),
        source_filename=policy.source_filename,
        extraction_confidence=policy.extraction_confidence,
        clause_count=len(clauses),
        ai_summary=policy.ai_summary,
        created_at=policy.created_at,
        extracted_schedules=policy.extracted_schedules_json,
        clauses=clauses,
    )


async def create_policy_structured(
    db: AsyncSession,
    *,
    payload: PolicyCreateIn,
    actor: Actor,
    llm_router: LLMRouter,
    settings: Settings,
    source_filename: str = "structured_api.json",
    raw_text: str = "",
    content_sha256: str = "",
    extraction_confidence: float = 0.98,
) -> Policy:
    """Persist a structured policy with indexed clause embeddings and audit entry."""
    existing = (
        await db.execute(select(Policy).where(Policy.policy_number == payload.policy_number))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Policy '{payload.policy_number}' already exists.",
        )

    digest = content_sha256 or hashlib.sha256(
        f"{payload.policy_number}:{payload.named_insured}:{payload.effective_date}".encode()
    ).hexdigest()

    llm_res = await llm_router.generate(
        prompt=(
            f"Policy {payload.policy_number} ({payload.line_of_business}) for "
            f"{payload.named_insured}: occurrence limit ${payload.per_occurrence_limit:,.2f}, "
            f"deductible ${payload.deductible:,.2f}, {len(payload.clauses)} indexed clauses."
        ),
        system_prompt="Summarize commercial insurance policy structure concisely.",
        task_type="policy_intake",
    )

    policy = Policy(
        policy_number=payload.policy_number.strip(),
        carrier_name=payload.carrier_name.strip(),
        named_insured=payload.named_insured.strip(),
        insured_address=payload.insured_address.strip(),
        line_of_business=payload.line_of_business.strip().lower(),
        acord_form_type=payload.acord_form_type.strip(),
        effective_date=payload.effective_date,
        expiration_date=payload.expiration_date,
        status=payload.status,
        per_occurrence_limit=quantize_money(payload.per_occurrence_limit),
        aggregate_limit=quantize_money(payload.aggregate_limit),
        deductible=quantize_money(payload.deductible),
        annual_premium=quantize_money(payload.annual_premium),
        source_filename=source_filename,
        content_sha256=digest,
        raw_text=raw_text,
        extracted_schedules_json=payload.schedules,
        extraction_confidence=extraction_confidence,
        ai_summary=llm_res.content,
    )
    db.add(policy)
    await db.flush()

    for item in payload.clauses:
        keywords = item.keywords or extract_keywords(f"{item.title} {item.clause_text}")
        vector = embed_text(
            f"{item.clause_type} {item.section_ref} {item.title} {item.clause_text}",
            dims=settings.embedding_dimensions,
        )
        clause = PolicyClause(
            policy_id=policy.id,
            clause_type=item.clause_type,
            section_ref=item.section_ref.strip(),
            page_number=item.page_number,
            title=item.title.strip(),
            clause_text=item.clause_text.strip(),
            monetary_limit=(
                quantize_money(item.monetary_limit) if item.monetary_limit is not None else None
            ),
            deductible_override=(
                quantize_money(item.deductible_override)
                if item.deductible_override is not None
                else None
            ),
            keywords_json=keywords,
            embedding_json=vector,
        )
        db.add(clause)

    await record_audit_event(
        db,
        event_type="policy.ingested",
        actor=actor,
        entity_type="policy",
        entity_id=policy.id,
        action="ingested",
        details={
            "policy_number": policy.policy_number,
            "named_insured": policy.named_insured,
            "line_of_business": policy.line_of_business,
            "clause_count": len(payload.clauses),
            "source_filename": source_filename,
        },
    )
    await db.commit()

    loaded = (
        await db.execute(
            select(Policy).options(selectinload(Policy.clauses)).where(Policy.id == policy.id)
        )
    ).scalar_one()
    return loaded


async def ingest_uploaded_policy_file(
    db: AsyncSession,
    *,
    filename: str,
    data: bytes,
    actor: Actor,
    llm_router: LLMRouter,
    settings: Settings,
) -> Policy:
    """Parse an uploaded ACORD/declaration PDF, TXT, or JSON and index all clauses."""
    pages = extract_pages_from_bytes(filename, data)
    parsed = parse_policy_document(pages, filename)
    digest = hashlib.sha256(data).hexdigest()

    from app.intake.schemas import PolicyClauseIn

    clause_inputs = [
        PolicyClauseIn(
            clause_type=c.clause_type,  # type: ignore[arg-type]
            section_ref=c.section_ref,
            page_number=c.page_number,
            title=c.title,
            clause_text=c.clause_text,
            monetary_limit=float(c.monetary_limit) if c.monetary_limit is not None else None,
            deductible_override=(
                float(c.deductible_override) if c.deductible_override is not None else None
            ),
            keywords=c.keywords,
        )
        for c in parsed.clauses
    ]

    payload = PolicyCreateIn(
        policy_number=parsed.policy_number,
        carrier_name=parsed.carrier_name,
        named_insured=parsed.named_insured,
        insured_address=parsed.insured_address,
        line_of_business=parsed.line_of_business,
        acord_form_type=parsed.acord_form_type,
        effective_date=parsed.effective_date,
        expiration_date=parsed.expiration_date,
        status="active",
        per_occurrence_limit=float(parsed.per_occurrence_limit),
        aggregate_limit=float(parsed.aggregate_limit),
        deductible=float(parsed.deductible),
        annual_premium=float(parsed.annual_premium),
        schedules=parsed.schedules,
        clauses=clause_inputs,
    )
    return await create_policy_structured(
        db,
        payload=payload,
        actor=actor,
        llm_router=llm_router,
        settings=settings,
        source_filename=filename,
        raw_text=parsed.raw_text,
        content_sha256=digest,
        extraction_confidence=parsed.extraction_confidence,
    )


async def list_policies_with_counts(db: AsyncSession) -> list[PolicySummaryOut]:
    """List policies ordered newest first with clause counts."""
    policies = list(
        (await db.execute(select(Policy).order_by(Policy.created_at.desc()))).scalars().all()
    )
    counts_rows = (
        await db.execute(
            select(PolicyClause.policy_id, func.count(PolicyClause.id)).group_by(
                PolicyClause.policy_id
            )
        )
    ).all()
    counts_map = {pid: cnt for pid, cnt in counts_rows}
    return [serialize_policy_summary(p, counts_map.get(p.id, 0)) for p in policies]


async def search_clauses_hybrid(
    db: AsyncSession,
    *,
    query: str,
    policy_id: str | None,
    clause_type: str | None,
    limit: int,
    settings: Settings,
) -> list[ClauseSearchResultOut]:
    """Rank indexed clauses using cosine similarity plus normalized keyword overlap."""
    stmt = select(PolicyClause, Policy).join(Policy, Policy.id == PolicyClause.policy_id)
    if policy_id:
        stmt = stmt.where(PolicyClause.policy_id == policy_id)
    if clause_type:
        stmt = stmt.where(PolicyClause.clause_type == clause_type.strip().lower())

    rows = (await db.execute(stmt)).all()
    query_vec = embed_text(query, dims=settings.embedding_dimensions)
    query_tokens = set(tokenize(query))
    query_lower = query.lower().strip()

    scored: list[ClauseSearchResultOut] = []
    for clause, policy in rows:
        sim = cosine_similarity(query_vec, clause.embedding_json)
        clause_tokens = set(clause.keywords_json) | set(
            tokenize(f"{clause.title} {clause.clause_text}")
        )
        overlap = (
            len(query_tokens & clause_tokens) / max(len(query_tokens), 1)
            if query_tokens
            else 0.0
        )
        phrase_boost = 0.2 if query_lower in f"{clause.title} {clause.clause_text}".lower() else 0.0
        score = round(min(1.0, max(0.0, sim * 0.55 + overlap * 0.45 + phrase_boost)), 4)
        if score <= 0.02 and query_tokens:
            continue
        scored.append(
            ClauseSearchResultOut(
                clause_id=clause.id,
                policy_id=policy.id,
                policy_number=policy.policy_number,
                named_insured=policy.named_insured,
                clause_type=clause.clause_type,
                section_ref=clause.section_ref,
                page_number=clause.page_number,
                title=clause.title,
                clause_text=clause.clause_text,
                monetary_limit=(
                    float(clause.monetary_limit) if clause.monetary_limit is not None else None
                ),
                deductible_override=(
                    float(clause.deductible_override)
                    if clause.deductible_override is not None
                    else None
                ),
                score=score,
                citation=(
                    f"{policy.policy_number} · Page {clause.page_number} · "
                    f"{clause.section_ref} — {clause.title}"
                ),
            )
        )

    scored.sort(key=lambda item: (-item.score, item.page_number, item.section_ref))
    return scored[:limit]
