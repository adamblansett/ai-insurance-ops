from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from tests.conftest import MANAGER_HEADERS, UNDERWRITER_HEADERS, make_test_app


@pytest.mark.asyncio
async def test_demo_seed_overview_hitl_approvals_and_audit_tamper_detection(
    tmp_path: Path,
) -> None:
    test_app = make_test_app(tmp_path)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed demo dataset
        seed1 = await client.post(
            "/api/v1/seed/demo",
            headers=MANAGER_HEADERS,
            json={"reset": False},
        )
        assert seed1.status_code == 200
        assert seed1.json()["status"] == "seeded"
        assert seed1.json()["policies"] == 3
        assert seed1.json()["claims"] == 4

        # Idempotent second call skips
        seed2 = await client.post(
            "/api/v1/seed/demo",
            headers=MANAGER_HEADERS,
            json={"reset": False},
        )
        assert seed2.status_code == 200
        assert seed2.json()["status"] == "skipped"

        # Overview KPIs populated
        ov = await client.get("/api/v1/overview", headers=MANAGER_HEADERS)
        assert ov.status_code == 200
        ov_data = ov.json()
        assert ov_data["policies_count"] == 3
        assert ov_data["indexed_clauses_count"] == 13
        assert ov_data["claims_count"] == 4
        assert ov_data["siu_flagged_claims_count"] >= 1
        assert ov_data["verifications_count"] == 4
        assert ov_data["submissions_count"] == 3
        assert ov_data["pending_approvals_count"] >= 5
        assert ov_data["audit_chain_valid"] is True

        # Fetch approvals and test each entity type's side effect
        approvals = (
            await client.get("/api/v1/audit/approvals?status=pending", headers=MANAGER_HEADERS)
        ).json()

        siu_app = next(a for a in approvals if a["entity_type"] == "siu_referral")
        reserve_app = next(a for a in approvals if a["entity_type"] == "claim_reserve")
        cov_app = next(a for a in approvals if a["entity_type"] == "coverage_determination")
        uw_decline_app = next(
            a
            for a in approvals
            if a["entity_type"] == "underwriting_decision" and a["action_requested"] == "uw_decline"
        )

        # Reject SIU referral -> moves queue back to field_property and status to triaged
        rej_siu = await client.post(
            f"/api/v1/audit/approvals/{siu_app['id']}/decide",
            headers=MANAGER_HEADERS,
            json={"decision": "rejected", "notes": "Verified legitimate telemetry"},
        )
        assert rej_siu.status_code == 200
        siu_claim = (
            await client.get(f"/api/v1/claims/{siu_app['entity_id']}", headers=MANAGER_HEADERS)
        ).json()
        assert siu_claim["triage_status"] == "triaged"
        assert siu_claim["adjuster_queue"] == "field_property"

        # Approve reserve -> claim triage_status becomes approved
        app_res = await client.post(
            f"/api/v1/audit/approvals/{reserve_app['id']}/decide",
            headers=MANAGER_HEADERS,
            json={"decision": "approved", "notes": "Reserve approved"},
        )
        assert app_res.status_code == 200
        res_claim = (
            await client.get(
                f"/api/v1/claims/{reserve_app['entity_id']}", headers=MANAGER_HEADERS
            )
        ).json()
        assert res_claim["triage_status"] == "approved"

        # Duplicate decision returns 409 Conflict
        dup_res = await client.post(
            f"/api/v1/audit/approvals/{reserve_app['id']}/decide",
            headers=MANAGER_HEADERS,
            json={"decision": "rejected"},
        )
        assert dup_res.status_code == 409

        # Approve coverage determination -> verification status becomes approved
        app_cov = await client.post(
            f"/api/v1/audit/approvals/{cov_app['id']}/decide",
            headers=MANAGER_HEADERS,
            json={"decision": "approved"},
        )
        assert app_cov.status_code == 200
        ver_item = (
            await client.get(
                f"/api/v1/coverage/verifications/{cov_app['entity_id']}",
                headers=MANAGER_HEADERS,
            )
        ).json()
        assert ver_item["status"] == "approved"

        # Underwriter approves uw_decline -> submission status becomes declined
        app_uw = await client.post(
            f"/api/v1/audit/approvals/{uw_decline_app['id']}/decide",
            headers=UNDERWRITER_HEADERS,
            json={"decision": "approved", "notes": "Confirm decline due to loss ratio"},
        )
        assert app_uw.status_code == 200
        sub_item = (
            await client.get(
                f"/api/v1/underwriting/submissions/{uw_decline_app['entity_id']}",
                headers=UNDERWRITER_HEADERS,
            )
        ).json()
        assert sub_item["status"] == "declined"

        # Verify audit chain intact before tampering
        verify_ok = await client.get("/api/v1/audit/events/verify", headers=MANAGER_HEADERS)
        assert verify_ok.status_code == 200
        assert verify_ok.json()["valid"] is True
        assert verify_ok.json()["total_events"] >= 10

        # Simulate direct DB row tamper at sequence_no = 2
        async with test_app.state.session_factory() as session:
            await session.execute(
                text("UPDATE audit_events SET action = 'tampered' WHERE sequence_no = 2")
            )
            await session.commit()

        verify_bad = await client.get("/api/v1/audit/events/verify", headers=MANAGER_HEADERS)
        assert verify_bad.status_code == 200
        assert verify_bad.json()["valid"] is False
        assert verify_bad.json()["broken_sequence_no"] == 2
