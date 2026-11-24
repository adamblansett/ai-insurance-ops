from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import UNDERWRITER_HEADERS, make_test_app


@pytest.mark.asyncio
async def test_underwriting_completeness_loss_ratio_tiers_and_reanalyze(
    tmp_path: Path,
) -> None:
    test_app = make_test_app(tmp_path)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Preferred clean submission -> auto quote_ready
        pref = await client.post(
            "/api/v1/underwriting/submissions",
            headers=UNDERWRITER_HEADERS,
            json={
                "submission_number": "SUB-UW-PREF",
                "applicant_name": "CleanTech Robotics Inc",
                "broker_name": "Apex Brokers",
                "line_of_business": "commercial_property",
                "requested_effective_date": "2027-01-01",
                "requested_limit": 500000.0,
                "requested_deductible": 10000.0,
                "tiv_amount": 3000000.0,
                "prior_premium": 30000.0,
                "documents_submitted": [
                    "acord_125",
                    "acord_140",
                    "statement_of_values",
                    "loss_runs_5yr",
                    "protective_safeguards",
                ],
                "loss_history": [],
            },
        )
        assert pref.status_code == 201
        p_data = pref.json()
        assert p_data["completeness_score"] == 100.0
        assert p_data["missing_documents"] == []
        assert p_data["risk_tier"] == "preferred"
        assert p_data["recommended_action"] == "quote"
        assert p_data["status"] == "quoted_ready"
        assert p_data["indicated_premium"] == 28500.0  # 30k * 0.95

        # 2. High loss ratio + missing docs -> decline_recommended + HITL gate
        bad = await client.post(
            "/api/v1/underwriting/submissions",
            headers=UNDERWRITER_HEADERS,
            json={
                "submission_number": "SUB-UW-DECLINE",
                "applicant_name": "Legacy Clinic Group",
                "line_of_business": "cyber",
                "requested_effective_date": "2027-01-01",
                "requested_limit": 2000000.0,
                "requested_deductible": 5000.0,
                "prior_premium": 30000.0,
                "documents_submitted": ["cyber_application"],
                "loss_history": [
                    {
                        "loss_date": "2024-03-01",
                        "peril": "cyber_ransomware",
                        "status": "closed",
                        "paid_amount": 35000.0,
                        "reserve_amount": 0.0,
                    },
                    {
                        "loss_date": "2025-05-01",
                        "peril": "cyber_ransomware",
                        "status": "closed",
                        "paid_amount": 25000.0,
                        "reserve_amount": 0.0,
                    },
                    {
                        "loss_date": "2026-06-01",
                        "peril": "cyber_ransomware",
                        "status": "open",
                        "paid_amount": 50000.0,
                        "reserve_amount": 75000.0,
                    },
                ],
            },
        )
        assert bad.status_code == 201
        b_data = bad.json()
        assert b_data["completeness_score"] == 20.0
        assert "mfa_attestation" in b_data["missing_documents"]
        assert b_data["total_incurred_losses"] == 185000.0
        assert b_data["loss_ratio_pct"] > 200.0
        assert b_data["risk_tier"] == "decline_recommended"
        assert b_data["recommended_action"] == "decline"
        assert b_data["status"] == "pending_uw_approval"
        assert b_data["approval_id"] is not None

        # 3. Reanalyze a substandard submission after adding missing documents
        sub = await client.post(
            "/api/v1/underwriting/submissions",
            headers=UNDERWRITER_HEADERS,
            json={
                "submission_number": "SUB-UW-REANALYZE",
                "applicant_name": "Harbor Warehouse Co",
                "line_of_business": "commercial_property",
                "requested_effective_date": "2027-02-01",
                "requested_limit": 750000.0,
                "requested_deductible": 10000.0,
                "prior_premium": 40000.0,
                "documents_submitted": ["acord_125", "acord_140"],
                "loss_history": [
                    {
                        "loss_date": "2025-02-01",
                        "peril": "water_damage",
                        "status": "closed",
                        "paid_amount": 35000.0,
                        "reserve_amount": 0.0,
                    }
                ],
            },
        )
        assert sub.status_code == 201
        sub_id = sub.json()["id"]
        assert sub.json()["completeness_score"] == 40.0

        reanalyzed = await client.post(
            f"/api/v1/underwriting/submissions/{sub_id}/reanalyze",
            headers=UNDERWRITER_HEADERS,
            json={
                "documents_submitted": [
                    "statement_of_values",
                    "loss_runs_5yr",
                    "protective_safeguards",
                ]
            },
        )
        assert reanalyzed.status_code == 200
        assert reanalyzed.json()["completeness_score"] == 100.0
        assert reanalyzed.json()["missing_documents"] == []
        assert reanalyzed.json()["risk_score"] < sub.json()["risk_score"]
