from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import ADJUSTER_HEADERS, build_minimal_pdf, make_test_app


@pytest.mark.asyncio
async def test_multipage_pdf_intake_clause_search_and_coverage_outcomes(
    tmp_path: Path,
) -> None:
    test_app = make_test_app(tmp_path)
    transport = ASGITransport(app=test_app)

    pdf_bytes = build_minimal_pdf(
        [
            [
                "ACORD 140 COMMERCIAL PROPERTY DECLARATIONS",
                "Policy Number: POL-TEST-2026-777",
                "Carrier: Meridian Indemnity Insurance Co.",
                "Named Insured: Lakeside Cold Logistics LLC",
                "Line of Business: Commercial Property",
                "Effective Date: 2026-01-01",
                "Expiration Date: 2027-01-01",
                "Per Occurrence Limit: $1,000,000",
                "Aggregate Limit: $2,000,000",
                "Deductible: $5,000",
                "Annual Premium: $32,000",
                "Location: Warehouse A, 100 Harbor Rd - $1,000,000",
            ],
            [
                "Coverage Grant (Section I.B): Sudden Plumbing and Pipe Burst Discharge",
                (
                    "Covers sudden accidental water discharge from interior plumbing "
                    "or chilled pipes up to $1,000,000."
                ),
                "Exclusion (Exclusion B.1.g): Coastal Flood and Storm Surge Exclusion",
                (
                    "Excludes loss caused by flood, tidal wave, coastal storm surge, "
                    "or rising surface water."
                ),
            ],
            [
                "Exclusion (Exclusion B.1.h): Water Backup and Sewer Drain Exclusion",
                (
                    "Excludes water that backs up through a sewer, drain, or sump pump "
                    "unless endorsed."
                ),
                "Endorsement (Endorsement CP 10 32): Water Backup and Sump Overflow Buy-Back",
                (
                    "Extends coverage for sewer, drain, or sump water backup up to a "
                    "sublimit of $50,000 with deductible override $2,500."
                ),
                "Condition (Condition IV.1): 72-Hour Notice Requirement for Cyber Events",
                (
                    "Insured must notify carrier within 72 hours of discovering an "
                    "unauthorized network event."
                ),
            ],
        ]
    )

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        upload = await client.post(
            "/api/v1/intake/policies/upload",
            headers=ADJUSTER_HEADERS,
            files={"file": ("lakeside_policy.pdf", pdf_bytes, "application/pdf")},
        )
        assert upload.status_code == 201
        pol = upload.json()
        assert pol["policy_number"] == "POL-TEST-2026-777"
        assert pol["named_insured"] == "Lakeside Cold Logistics LLC"
        assert pol["per_occurrence_limit"] == 1000000.0
        assert pol["deductible"] == 5000.0
        assert pol["clause_count"] >= 4

        # Hybrid search finds Water Backup endorsement on Page 3
        search = await client.post(
            "/api/v1/intake/clauses/search",
            headers=ADJUSTER_HEADERS,
            json={"query": "water backup sump overflow sublimit", "policy_id": pol["id"]},
        )
        assert search.status_code == 200
        hits = search.json()
        assert hits
        assert any("Page 3" in h["citation"] and "CP 10 32" in h["citation"] for h in hits)

        # 1. Clean covered pipe burst claim -> covered, net payout = 18000 - 5000 = 13000
        clm_pipe = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-COV-PIPE",
                "policy_number_reported": "POL-TEST-2026-777",
                "claimant_name": "Lakeside Cold Logistics LLC",
                "loss_date": "2026-06-10",
                "reported_date": "2026-06-11",
                "peril_type": "water_damage",
                "loss_description": "Burst interior plumbing pipe flooded packaging room.",
                "claimed_amount": 18000.0,
            },
        )
        assert clm_pipe.status_code == 201
        ver_pipe = await client.post(
            "/api/v1/coverage/verify",
            headers=ADJUSTER_HEADERS,
            json={"claim_id": clm_pipe.json()["id"]},
        )
        assert ver_pipe.status_code == 201
        vp = ver_pipe.json()
        assert vp["determination"] == "covered"
        assert vp["applicable_deductible"] == 5000.0
        assert vp["estimated_covered_payout"] == 13000.0
        assert vp["excess_over_limit"] == 0.0
        assert vp["requires_hitl_review"] is False

        # 2. Sewer/sump water backup -> Endorsement CP 10 32 overrides exclusion B.1.h!
        # Net: 72,500 - 2,500 override ded = 70,000 -> capped at 50,000 sublimit -> 20,000 excess!
        clm_backup = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-COV-BACKUP",
                "policy_number_reported": "POL-TEST-2026-777",
                "claimant_name": "Lakeside Cold Logistics LLC",
                "loss_date": "2026-07-02",
                "reported_date": "2026-07-03",
                "peril_type": "water_damage",
                "loss_description": "Sewer drain and sump pump water backup damaged lower stock.",
                "claimed_amount": 72500.0,
            },
        )
        assert clm_backup.status_code == 201
        ver_backup = await client.post(
            "/api/v1/coverage/verify",
            headers=ADJUSTER_HEADERS,
            json={"claim_id": clm_backup.json()["id"]},
        )
        assert ver_backup.status_code == 201
        vb = ver_backup.json()
        assert vb["determination"] == "partial_coverage"
        assert vb["applicable_limit"] == 50000.0
        assert vb["applicable_deductible"] == 2500.0
        assert vb["estimated_covered_payout"] == 50000.0
        assert vb["excess_over_limit"] == 20000.0
        assert any(ex["overridden_by"] for ex in vb["triggered_exclusions"])
        assert any("Page 3" in c and "CP 10 32" in c for c in vb["citations"])

        # 3. Coastal flood claim -> excluded citing Page 2 Exclusion B.1.g
        clm_flood = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-COV-FLOOD",
                "policy_number_reported": "POL-TEST-2026-777",
                "claimant_name": "Lakeside Cold Logistics LLC",
                "loss_date": "2026-08-15",
                "reported_date": "2026-08-16",
                "peril_type": "flood",
                "loss_description": "Coastal storm surge and tidal flood inundated dock.",
                "claimed_amount": 95000.0,
            },
        )
        assert clm_flood.status_code == 201
        ver_flood = await client.post(
            "/api/v1/coverage/verify",
            headers=ADJUSTER_HEADERS,
            json={"claim_id": clm_flood.json()["id"]},
        )
        assert ver_flood.status_code == 201
        vf = ver_flood.json()
        assert vf["determination"] == "excluded"
        assert vf["estimated_covered_payout"] == 0.0
        assert vf["requires_hitl_review"] is True
        assert any("Page 2" in c and "B.1.g" in c for c in vf["citations"])

        # 4. Loss outside policy period -> policy_inactive
        clm_old = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-COV-INACTIVE",
                "policy_number_reported": "POL-TEST-2026-777",
                "claimant_name": "Lakeside Cold Logistics LLC",
                "loss_date": "2025-11-15",
                "reported_date": "2025-11-16",
                "peril_type": "fire",
                "loss_description": "Minor heater smoke event.",
                "claimed_amount": 6000.0,
            },
        )
        assert clm_old.status_code == 201
        ver_old = await client.post(
            "/api/v1/coverage/verify",
            headers=ADJUSTER_HEADERS,
            json={"claim_id": clm_old.json()["id"]},
        )
        assert ver_old.status_code == 201
        assert ver_old.json()["determination"] == "policy_inactive"
        assert ver_old.json()["policy_in_force"] is False

        # 5. Late notice > 72h -> reservation_of_rights
        clm_late = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-COV-LATE",
                "policy_number_reported": "POL-TEST-2026-777",
                "claimant_name": "Lakeside Cold Logistics LLC",
                "loss_date": "2026-04-01",
                "reported_date": "2026-04-10",
                "peril_type": "water_damage",
                "loss_description": "Pipe leak in office corridor.",
                "claimed_amount": 8000.0,
            },
        )
        assert clm_late.status_code == 201
        ver_late = await client.post(
            "/api/v1/coverage/verify",
            headers=ADJUSTER_HEADERS,
            json={"claim_id": clm_late.json()["id"]},
        )
        assert ver_late.status_code == 201
        assert ver_late.json()["determination"] == "reservation_of_rights"
        assert ver_late.json()["requires_hitl_review"] is True
