from datetime import date
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.auth import create_access_token
from app.core.config import Settings
from app.llm.pii import redact_pii
from app.llm.router import LLMRouter
from tests.conftest import (
    ADJUSTER_HEADERS,
    MANAGER_HEADERS,
    UNDERWRITER_HEADERS,
    VIEWER_HEADERS,
    make_test_app,
)


@pytest.mark.asyncio
async def test_jwt_auth_and_require_token_enforcement(tmp_path: Path) -> None:
    test_app = make_test_app(
        tmp_path,
        auth_require_token=True,
        auth_secret_key="super-secure-test-secret-key-at-least-32-bytes",
    )
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unauthenticated dev headers must be rejected when auth_require_token=True
        denied = await client.get("/api/v1/auth/me", headers=MANAGER_HEADERS)
        assert denied.status_code == 401

        # Issue token via dev auth endpoint
        tok_resp = await client.post(
            "/api/v1/auth/token",
            json={"email": "lead@insops.test", "role": "claims_manager"},
        )
        assert tok_resp.status_code == 200
        token = tok_resp.json()["access_token"]

        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == "lead@insops.test"
        assert me.json()["role"] == "claims_manager"
        assert me.json()["auth_method"] == "bearer_token"

        # Tampered token rejected
        bad = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}tampered"},
        )
        assert bad.status_code == 401

        # Expired token rejected
        expired = create_access_token(
            "lead@insops.test",
            "claims_manager",
            test_app.state.settings.auth_secret_key,
            ttl_seconds=-10,
        )
        exp_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert exp_resp.status_code == 401


@pytest.mark.asyncio
async def test_rbac_matrix_across_roles(tmp_path: Path) -> None:
    test_app = make_test_app(tmp_path)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Viewer cannot ingest a policy or submit a claim
        viewer_pol = await client.post(
            "/api/v1/intake/policies",
            headers=VIEWER_HEADERS,
            json={
                "policy_number": "POL-VIEW-1",
                "named_insured": "Test Co",
                "effective_date": "2026-01-01",
                "expiration_date": "2027-01-01",
                "per_occurrence_limit": 100000,
                "aggregate_limit": 200000,
            },
        )
        assert viewer_pol.status_code == 403

        # Adjuster cannot submit underwriting submission
        adj_uw = await client.post(
            "/api/v1/underwriting/submissions",
            headers=ADJUSTER_HEADERS,
            json={
                "submission_number": "SUB-ADJ-1",
                "applicant_name": "Acme Corp",
                "line_of_business": "commercial_property",
                "requested_effective_date": str(date(2027, 1, 1)),
                "requested_limit": 500000,
            },
        )
        assert adj_uw.status_code == 403

        # Create a high-reserve claim (>= 25000) as adjuster -> triggers claim_reserve approval
        claim_resp = await client.post(
            "/api/v1/claims",
            headers=ADJUSTER_HEADERS,
            json={
                "claim_number": "CLM-RBAC-1",
                "policy_number_reported": "POL-MISSING-1",
                "claimant_name": "Test Claimant",
                "loss_date": "2026-05-01",
                "reported_date": "2026-05-02",
                "peril_type": "fire",
                "loss_description": "Warehouse electrical fire.",
                "claimed_amount": 40000.0,
            },
        )
        assert claim_resp.status_code == 201
        approval_id = claim_resp.json()["approval_id"]
        assert approval_id is not None

        # Adjuster cannot approve claim_reserve
        adj_decide = await client.post(
            f"/api/v1/audit/approvals/{approval_id}/decide",
            headers=ADJUSTER_HEADERS,
            json={"decision": "approved"},
        )
        assert adj_decide.status_code == 403

        # Underwriter cannot approve claim_reserve
        uw_decide = await client.post(
            f"/api/v1/audit/approvals/{approval_id}/decide",
            headers=UNDERWRITER_HEADERS,
            json={"decision": "approved"},
        )
        assert uw_decide.status_code == 403

        # Claims manager can approve claim_reserve
        mgr_decide = await client.post(
            f"/api/v1/audit/approvals/{approval_id}/decide",
            headers=MANAGER_HEADERS,
            json={"decision": "approved", "notes": "Reserve verified"},
        )
        assert mgr_decide.status_code == 200
        assert mgr_decide.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_insurance_pii_redaction_and_cloud_llm_scrubbing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = (
        "Insured Jane Doe (SSN 123-45-6789, FEIN 94-1234567, DOB 1982-04-15, "
        "DL D902-4412-88, Member ID MEM-77312) reported VIN: 1HGCM82633A004352 "
        "claim from jane@insops.example or 415-555-0199 with card 4111-1111-1111-1111."
    )
    res = redact_pii(sample)
    assert "[REDACTED_SSN]" in res.redacted_text
    assert "[REDACTED_FEIN]" in res.redacted_text
    assert "[REDACTED_DOB]" in res.redacted_text
    assert "[REDACTED_DL]" in res.redacted_text
    assert "[REDACTED_MEMBER_ID]" in res.redacted_text
    assert "[REDACTED_VIN]" in res.redacted_text
    assert "[REDACTED_EMAIL]" in res.redacted_text
    assert "[REDACTED_PHONE]" in res.redacted_text
    assert "[REDACTED_CARD]" in res.redacted_text
    assert "123-45-6789" not in res.redacted_text
    assert "1HGCM82633A004352" not in res.redacted_text
    assert res.total_redactions == 9

    captured_payloads: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "candidates": [
                    {"content": {"parts": [{"text": "Cloud response ok"}]}}
                ]
            }

    async def fake_post(
        self: httpx.AsyncClient, url: str, **kwargs: object
    ) -> FakeResponse:
        _ = url
        captured_payloads.append(str(kwargs.get("json")))
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    router = LLMRouter(
        Settings(
            llm_default_provider="gemini",
            llm_fallback_providers="mock",
            gemini_api_key="test-key",
            llm_redact_pii_for_cloud=True,
        )
    )
    out = await router.generate(prompt=sample, task_type="claims_triage")
    assert out.provider == "gemini"
    assert out.pii_redacted is True
    assert out.redaction_count == 9
    assert captured_payloads
    assert "123-45-6789" not in captured_payloads[0]
    assert "1HGCM82633A004352" not in captured_payloads[0]
    assert "[REDACTED_SSN]" in captured_payloads[0]
