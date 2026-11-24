from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_audit_event
from app.claims.schemas import ClaimCreateIn
from app.claims.service import submit_and_triage_claim
from app.core.auth import Actor
from app.core.config import Settings
from app.coverage.service import run_coverage_verification
from app.db.models import (
    ApprovalRequest,
    AuditEvent,
    Claim,
    CoverageVerification,
    Policy,
    PolicyClause,
    UnderwritingSubmission,
)
from app.intake.schemas import PolicyClauseIn, PolicyCreateIn
from app.intake.service import create_policy_structured
from app.llm.router import LLMRouter
from app.underwriting.schemas import LossRunEntryIn, SubmissionCreateIn
from app.underwriting.service import create_and_analyze_submission


async def seed_demo_dataset(
    db: AsyncSession,
    *,
    llm_router: LLMRouter,
    settings: Settings,
    actor: Actor,
    reset: bool = False,
) -> dict[str, int | str]:
    """Populate realistic insurance policies, FNOL claims, verifications, and UW submissions."""
    existing_policies = int((await db.execute(select(func.count(Policy.id)))).scalar() or 0)
    if existing_policies > 0 and not reset:
        return {
            "status": "skipped",
            "message": "Demo dataset already present; pass reset=true to reload.",
            "policies": existing_policies,
        }

    if reset:
        await db.execute(delete(CoverageVerification))
        await db.execute(delete(Claim))
        await db.execute(delete(PolicyClause))
        await db.execute(delete(Policy))
        await db.execute(delete(UnderwritingSubmission))
        await db.execute(delete(ApprovalRequest))
        await db.execute(delete(AuditEvent))
        await db.commit()

    # 1. Three representative policies with 13 page-cited clauses
    pol_cp = await create_policy_structured(
        db,
        payload=PolicyCreateIn(
            policy_number="POL-CP-2026-1001",
            carrier_name="Beacon Commercial Indemnity",
            named_insured="Harborview Cold Storage LLC",
            insured_address="420 Pier Ave, Portland, ME 04101",
            line_of_business="commercial_property",
            acord_form_type="ACORD 140",
            effective_date=date(2026, 1, 1),
            expiration_date=date(2027, 1, 1),
            status="active",
            per_occurrence_limit=2000000.0,
            aggregate_limit=4000000.0,
            deductible=5000.0,
            annual_premium=48500.0,
            schedules=[
                {
                    "category": "location",
                    "description": "Cold Storage Facility #1 — 420 Pier Ave",
                    "scheduled_value": 2000000.0,
                }
            ],
            clauses=[
                PolicyClauseIn(
                    clause_type="coverage_grant",
                    section_ref="Section I.A",
                    page_number=1,
                    title="Building and Business Personal Property Coverage",
                    clause_text=(
                        "Covers direct physical loss or damage to scheduled refrigerated "
                        "warehouse structures and machinery unless specifically excluded."
                    ),
                    monetary_limit=2000000.0,
                ),
                PolicyClauseIn(
                    clause_type="coverage_grant",
                    section_ref="Section I.B.3",
                    page_number=3,
                    title="Accidental Plumbing Discharge and Burst Pipe Water Damage",
                    clause_text=(
                        "Provides coverage for sudden and accidental water discharge or leakage "
                        "from building plumbing, chilled-water piping, or automatic sprinklers."
                    ),
                    monetary_limit=2000000.0,
                ),
                PolicyClauseIn(
                    clause_type="exclusion",
                    section_ref="Exclusion B.1.g",
                    page_number=7,
                    title="Flood, Surface Water, Storm Surge, and Tidal Wave Exclusion",
                    clause_text=(
                        "We will not pay for loss or damage caused directly or indirectly by "
                        "flood, coastal storm surge, waves, tidal water, overflow of any body "
                        "of water, or surface water inundation."
                    ),
                ),
                PolicyClauseIn(
                    clause_type="exclusion",
                    section_ref="Exclusion B.1.h",
                    page_number=8,
                    title="Water Backup and Sewer or Drain Overflow Exclusion",
                    clause_text=(
                        "Excludes loss caused by water that backs up or overflows from a sewer, "
                        "drain, or sump pump unless endorsed."
                    ),
                ),
                PolicyClauseIn(
                    clause_type="endorsement",
                    section_ref="Endorsement CP 10 32",
                    page_number=12,
                    title="Water Backup and Sump Overflow Buy-Back Endorsement",
                    clause_text=(
                        "Notwithstanding Exclusion B.1.h, this endorsement extends coverage for "
                        "sewer, drain, or sump water backup up to a sublimit of $50,000 with "
                        "a $2,500 deductible override."
                    ),
                    monetary_limit=50000.0,
                    deductible_override=2500.0,
                ),
            ],
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
        source_filename="harborview_acord_140.pdf",
    )

    pol_cyb = await create_policy_structured(
        db,
        payload=PolicyCreateIn(
            policy_number="POL-CYB-2026-2040",
            carrier_name="Aegis Cyber Underwriters",
            named_insured="Meridian Health Clinics PC",
            insured_address="880 Medical Plaza, Columbus, OH 43215",
            line_of_business="cyber",
            acord_form_type="ACORD 125",
            effective_date=date(2026, 10, 15),
            expiration_date=date(2027, 10, 15),
            status="active",
            per_occurrence_limit=1000000.0,
            aggregate_limit=2000000.0,
            deductible=10000.0,
            annual_premium=36000.0,
            clauses=[
                PolicyClauseIn(
                    clause_type="coverage_grant",
                    section_ref="Insuring Agreement A",
                    page_number=1,
                    title="Cyber Extortion and Ransomware Incident Response",
                    clause_text=(
                        "Covers forensic investigation, extortion negotiation, and ransomware "
                        "decryption expenses arising from unauthorized network encryption."
                    ),
                    monetary_limit=1000000.0,
                ),
                PolicyClauseIn(
                    clause_type="coverage_grant",
                    section_ref="Insuring Agreement B",
                    page_number=2,
                    title="Data Restoration and System Recovery Sublimit",
                    clause_text=(
                        "Covers electronic data restoration and server rebuild costs up to "
                        "a $500,000 sublimit."
                    ),
                    monetary_limit=500000.0,
                ),
                PolicyClauseIn(
                    clause_type="condition",
                    section_ref="Condition IV.2",
                    page_number=5,
                    title="72-Hour Cyber Incident Notice Condition",
                    clause_text=(
                        "As a condition precedent to coverage, the Named Insured must notify "
                        "the Insurer within 72 hours of discovering any ransomware or "
                        "network intrusion event."
                    ),
                ),
                PolicyClauseIn(
                    clause_type="exclusion",
                    section_ref="Exclusion E.4",
                    page_number=6,
                    title="Unpatched End-of-Life Infrastructure Exclusion",
                    clause_text=(
                        "Excludes loss arising from known critical vulnerabilities left "
                        "unpatched beyond 90 days."
                    ),
                ),
            ],
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
        source_filename="meridian_cyber_policy.pdf",
    )

    pol_cgl = await create_policy_structured(
        db,
        payload=PolicyCreateIn(
            policy_number="POL-CGL-2026-3090",
            carrier_name="Granite Peak Liability Corp.",
            named_insured="Summit Builders & Contractors Inc.",
            insured_address="1500 Industrial Blvd, Denver, CO 80202",
            line_of_business="commercial_general_liability",
            acord_form_type="ACORD 126",
            effective_date=date(2026, 2, 1),
            expiration_date=date(2027, 2, 1),
            status="active",
            per_occurrence_limit=1000000.0,
            aggregate_limit=2000000.0,
            deductible=2500.0,
            annual_premium=29400.0,
            clauses=[
                PolicyClauseIn(
                    clause_type="coverage_grant",
                    section_ref="Coverage A",
                    page_number=1,
                    title="Bodily Injury and Property Damage Liability",
                    clause_text=(
                        "Pays sums the insured becomes legally obligated to pay as damages "
                        "because of third-party bodily injury or property damage on "
                        "covered premises."
                    ),
                    monetary_limit=1000000.0,
                ),
                PolicyClauseIn(
                    clause_type="sublimit",
                    section_ref="Coverage C",
                    page_number=4,
                    title="Premises Medical Payments Sublimit",
                    clause_text=(
                        "Covers reasonable first-aid and urgent medical expenses up to "
                        "a $15,000 sublimit regardless of fault."
                    ),
                    monetary_limit=15000.0,
                ),
                PolicyClauseIn(
                    clause_type="exclusion",
                    section_ref="Exclusion j.(5)",
                    page_number=9,
                    title="Faulty Workmanship and Defective Product Exclusion",
                    clause_text=(
                        "Excludes property damage to that particular part of real property "
                        "on which the insured is performing defective construction operations."
                    ),
                ),
                PolicyClauseIn(
                    clause_type="endorsement",
                    section_ref="Endorsement CG 20 10",
                    page_number=11,
                    title="Additional Insured — Owners, Lessees or Contractors",
                    clause_text=(
                        "Extends Coverage A insured status to scheduled project owners "
                        "for ongoing operations."
                    ),
                ),
            ],
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
        source_filename="summit_cgl_acord126.pdf",
    )

    # 2. Four representative FNOL claims + citation-grounded coverage verifications
    claim1 = await submit_and_triage_claim(
        db,
        payload=ClaimCreateIn(
            claim_number="CLM-2026-5001",
            policy_number_reported=pol_cp.policy_number,
            claimant_name="Harborview Cold Storage LLC",
            loss_date=date(2026, 8, 14),
            reported_date=date(2026, 8, 15),
            loss_location="Freezer Bay 3, 420 Pier Ave, Portland, ME",
            peril_type="water_damage",
            loss_description=(
                "Sudden burst overhead chilled-water plumbing pipe damaged racking "
                "and insulation in Freezer Bay 3."
            ),
            claimed_amount=85000.0,
            injuries_reported=False,
            police_report_filed=False,
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )
    await run_coverage_verification(
        db,
        claim_id=claim1.id,
        policy_id=pol_cp.id,
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )

    claim2 = await submit_and_triage_claim(
        db,
        payload=ClaimCreateIn(
            claim_number="CLM-2026-5002",
            policy_number_reported=pol_cp.policy_number,
            claimant_name="Harborview Cold Storage LLC",
            loss_date=date(2026, 9, 20),
            reported_date=date(2026, 9, 21),
            loss_location="South Loading Dock, 420 Pier Ave, Portland, ME",
            peril_type="flood",
            loss_description=(
                "Coastal storm surge and rising tidal flood waters inundated lower "
                "loading bay refrigeration motors."
            ),
            claimed_amount=145000.0,
            injuries_reported=False,
            police_report_filed=False,
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )
    await run_coverage_verification(
        db,
        claim_id=claim2.id,
        policy_id=pol_cp.id,
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )

    claim3 = await submit_and_triage_claim(
        db,
        payload=ClaimCreateIn(
            claim_number="CLM-2026-5003",
            policy_number_reported=pol_cyb.policy_number,
            claimant_name="Meridian Health Clinics PC",
            loss_date=date(2026, 10, 28),
            reported_date=date(2026, 11, 12),
            loss_location="Primary EHR Cluster, Columbus, OH",
            peril_type="cyber_ransomware",
            loss_description=(
                "Ransomware network encryption incident across clinic servers; initial "
                "log review shows inconsistent timeline and prior damage."
            ),
            claimed_amount=320000.0,
            injuries_reported=False,
            police_report_filed=True,
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )
    await run_coverage_verification(
        db,
        claim_id=claim3.id,
        policy_id=pol_cyb.id,
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )

    claim4 = await submit_and_triage_claim(
        db,
        payload=ClaimCreateIn(
            claim_number="CLM-2026-5004",
            policy_number_reported=pol_cgl.policy_number,
            claimant_name="Apex Site Inspector (Third-Party)",
            loss_date=date(2026, 11, 5),
            reported_date=date(2026, 11, 6),
            loss_location="1500 Industrial Blvd, Denver, CO",
            peril_type="bodily_injury",
            loss_description=(
                "Minor slip and fall on walkway near site entrance requiring urgent-care "
                "medical payments evaluation."
            ),
            claimed_amount=4800.0,
            injuries_reported=False,
            police_report_filed=False,
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )
    await run_coverage_verification(
        db,
        claim_id=claim4.id,
        policy_id=pol_cgl.id,
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )

    # 3. Three underwriting submissions spanning Preferred -> Substandard -> Decline
    await create_and_analyze_submission(
        db,
        payload=SubmissionCreateIn(
            submission_number="SUB-2026-8001",
            applicant_name="Cascade Precision Manufacturing",
            broker_name="Willis Northwest Brokers",
            line_of_business="commercial_property",
            requested_effective_date=date(2027, 1, 1),
            requested_limit=750000.0,
            requested_deductible=10000.0,
            annual_revenue=14200000.0,
            tiv_amount=6500000.0,
            prior_premium=42000.0,
            documents_submitted=[
                "acord_125",
                "acord_140",
                "statement_of_values",
                "loss_runs_5yr",
                "protective_safeguards",
            ],
            loss_history=[
                LossRunEntryIn(
                    loss_date=date(2024, 5, 11),
                    claim_number="LR-2024-112",
                    peril="wind_hail",
                    status="closed",
                    paid_amount=4500.0,
                    reserve_amount=0.0,
                    description="Minor warehouse roof flashing repair.",
                )
            ],
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )

    await create_and_analyze_submission(
        db,
        payload=SubmissionCreateIn(
            submission_number="SUB-2026-8002",
            applicant_name="Northstar Logistics Warehouse Group",
            broker_name="Midwest Risk Partners",
            line_of_business="commercial_property",
            requested_effective_date=date(2027, 1, 15),
            requested_limit=2500000.0,
            requested_deductible=10000.0,
            annual_revenue=22000000.0,
            tiv_amount=11000000.0,
            prior_premium=50000.0,
            documents_submitted=["acord_125", "acord_140", "loss_runs_5yr"],
            loss_history=[
                LossRunEntryIn(
                    loss_date=date(2023, 3, 18),
                    claim_number="LR-2023-201",
                    peril="water_damage",
                    status="closed",
                    paid_amount=38000.0,
                    reserve_amount=0.0,
                    description="Sprinkler head freeze rupture.",
                ),
                LossRunEntryIn(
                    loss_date=date(2024, 9, 4),
                    claim_number="LR-2024-309",
                    peril="theft",
                    status="closed",
                    paid_amount=32000.0,
                    reserve_amount=0.0,
                    description="Trailer yard pallet theft.",
                ),
                LossRunEntryIn(
                    loss_date=date(2026, 2, 22),
                    claim_number="LR-2026-414",
                    peril="fire",
                    status="open",
                    paid_amount=25000.0,
                    reserve_amount=40000.0,
                    description="Forklift battery charging bay smoke event.",
                ),
            ],
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )

    await create_and_analyze_submission(
        db,
        payload=SubmissionCreateIn(
            submission_number="SUB-2026-8003",
            applicant_name="Apex Regional Dental Network",
            broker_name="Summit Specialty Wholesale",
            line_of_business="cyber",
            requested_effective_date=date(2027, 2, 1),
            requested_limit=2000000.0,
            requested_deductible=5000.0,
            annual_revenue=18500000.0,
            tiv_amount=0.0,
            prior_premium=32000.0,
            documents_submitted=["cyber_application", "loss_runs_3yr"],
            loss_history=[
                LossRunEntryIn(
                    loss_date=date(2024, 7, 10),
                    claim_number="LR-CYB-01",
                    peril="cyber_ransomware",
                    status="closed",
                    paid_amount=45000.0,
                    reserve_amount=0.0,
                    description="Business email compromise wire loss.",
                ),
                LossRunEntryIn(
                    loss_date=date(2025, 11, 2),
                    claim_number="LR-CYB-02",
                    peril="cyber_ransomware",
                    status="closed",
                    paid_amount=22000.0,
                    reserve_amount=0.0,
                    description="Third-party patient portal exposure.",
                ),
                LossRunEntryIn(
                    loss_date=date(2026, 6, 19),
                    claim_number="LR-CYB-03",
                    peril="cyber_ransomware",
                    status="open",
                    paid_amount=65000.0,
                    reserve_amount=120000.0,
                    description="Unencrypted imaging server ransomware outbreak.",
                ),
            ],
        ),
        actor=actor,
        llm_router=llm_router,
        settings=settings,
    )

    await record_audit_event(
        db,
        event_type="seed.loaded",
        actor=actor,
        entity_type="workspace",
        entity_id="demo-dataset",
        action="seeded",
        details={"policies": 3, "claims": 4, "verifications": 4, "submissions": 3},
    )
    await db.commit()

    return {
        "status": "seeded",
        "message": (
            "Loaded 3 policies (13 clauses), 4 FNOL claims, 4 coverage verifications, "
            "and 3 underwriting submissions."
        ),
        "policies": 3,
        "claims": 4,
        "verifications": 4,
        "submissions": 3,
    }
