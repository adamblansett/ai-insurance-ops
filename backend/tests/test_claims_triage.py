from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import ADJUSTER_HEADERS, make_test_app


@pytest.mark.asyncio
async def test_fnol_triage_routing_siu_fraud_and_retriage(tmp_path: Path) -> None:
    test_app = make_test_app(tmp_path)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create an active policy first
        pol_resp = await client.post(
            "/api/v1/intake/policies",
            headers=ADJUSTER_HEADERS,
            json={
                "policy_number": "POL-TRIAGE-1",
                "named_insured": "Metro Fleet Co",
                "line_of_business": "commercial_property",
                "effective_date": "2026-10-01",
                "expiration_date": "2027-10-01",
                "per_occurrence_limit": 500000.0,
                "aggregate_limit": 1000000.0,
                "deductible": 2500.0,
            },
        )
        assert pol_resp.status_code == 201

        # 1. Fast-track claim (< $10k, clean dates)
        fast = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-FAST-1",
                "policy_number_reported": "POL-TRIAGE-1",
                "claimant_name": "Metro Fleet Co",
                "loss_date": "2026-11-15",
                "reported_date": "2026-11-16",
                "peril_type": "wind_hail",
                "loss_description": "Minor awning hail denting at loading entrance.",
                "claimed_amount": 6500.0,
            },
        )
        assert fast.status_code == 201
        f_data = fast.json()
        assert f_data["reserve_band"] == "fast_track_0_10k"
        assert f_data["adjuster_queue"] == "fast_track_desk"
        assert f_data["triage_status"] == "triaged"
        assert f_data["approval_id"] is None

        # 2. High-reserve claim (>= $25k) triggers claim_reserve HITL gate
        high = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-HIGH-1",
                "policy_number_reported": "POL-TRIAGE-1",
                "claimant_name": "Metro Fleet Co",
                "loss_date": "2026-11-10",
                "reported_date": "2026-11-11",
                "peril_type": "fire",
                "loss_description": "Compressor room electrical fire damaged control panels.",
                "claimed_amount": 60000.0,
            },
        )
        assert high.status_code == 201
        h_data = high.json()
        assert h_data["severity_tier"] == "high"
        assert h_data["reserve_band"] == "complex_50k_250k"
        assert h_data["recommended_reserve"] == 69000.0  # +15% LAE for fire peril
        assert h_data["triage_status"] == "pending_reserve_approval"
        assert h_data["approval_id"] is not None

        # 3. SIU fraud claim: early loss (10d) + theft w/o police report + suspicious cue
        siu = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-SIU-1",
                "policy_number_reported": "POL-TRIAGE-1",
                "claimant_name": "Metro Fleet Co",
                "loss_date": "2026-10-11",
                "reported_date": "2026-10-12",
                "peril_type": "theft",
                "loss_description": (
                    "Equipment theft paid cash only; inconsistent inventory records."
                ),
                "claimed_amount": 45000.0,
                "police_report_filed": False,
            },
        )
        assert siu.status_code == 201
        s_data = siu.json()
        codes = {ind["code"] for ind in s_data["fraud_indicators"]}
        expected_codes = {
            "EARLY_POLICY_LOSS",
            "NO_POLICE_REPORT_THEFT",
            "SUSPICIOUS_NARRATIVE_CUES",
        }
        assert expected_codes <= codes
        assert s_data["fraud_score"] >= 0.60
        assert s_data["adjuster_queue"] == "siu_investigation"
        assert s_data["triage_status"] == "pending_siu_review"
        assert s_data["approval_id"] is not None

        # 4. Duplicate claim within 7 days triggers DUPLICATE_LOSS_PATTERN
        dup = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-SIU-DUP",
                "policy_number_reported": "POL-TRIAGE-1",
                "claimant_name": "Metro Fleet Co",
                "loss_date": "2026-10-14",
                "reported_date": "2026-10-15",
                "peril_type": "theft",
                "loss_description": "Second tool theft claim at same depot.",
                "claimed_amount": 18000.0,
                "police_report_filed": True,
            },
        )
        assert dup.status_code == 201
        dup_codes = {ind["code"] for ind in dup.json()["fraud_indicators"]}
        assert "DUPLICATE_LOSS_PATTERN" in dup_codes

        # 5. Retriage after creating a previously-missing policy links policy_id
        orphan = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-ORPHAN-1",
                "policy_number_reported": "POL-LATE-BIND-1",
                "claimant_name": "Late Bind Co",
                "loss_date": "2026-08-01",
                "reported_date": "2026-08-02",
                "peril_type": "water_damage",
                "loss_description": "Small office leak.",
                "claimed_amount": 4000.0,
            },
        )
        assert orphan.status_code == 201
        assert orphan.json()["policy_id"] is None

        await client.post(
            "/api/v1/intake/policies",
            headers=ADJUSTER_HEADERS,
            json={
                "policy_number": "POL-LATE-BIND-1",
                "named_insured": "Late Bind Co",
                "effective_date": "2026-01-01",
                "expiration_date": "2027-01-01",
                "per_occurrence_limit": 250000.0,
                "aggregate_limit": 500000.0,
            },
        )
        retriaged = await client.post(
            f"/api/v1/claims/{orphan.json()['id']}/retriage",
            headers=ADJUSTER_HEADERS,
        )
        assert retriaged.status_code == 200
        assert retriaged.json()["policy_id"] is not None
