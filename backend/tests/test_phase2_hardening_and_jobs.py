from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.audit.service import record_audit_event, verify_audit_chain
from app.core.auth import Actor
from app.core.config import Settings
from app.intake.vector_store import format_pgvector_literal, is_postgres_session
from app.llm.router import _post_with_retry
from tests.conftest import ADJUSTER_HEADERS, MANAGER_HEADERS, build_minimal_pdf, make_test_app


@pytest.mark.asyncio
async def test_rate_limit_csp_and_health_metadata(tmp_path: Path) -> None:
    test_app = make_test_app(
        tmp_path,
        rate_limit_enabled=True,
        rate_limit_requests_per_minute=2,
        rate_limit_auth_per_minute=2,
    )
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health endpoints report phase 2 vector_backend + task_execution_mode & bypass rate limit
        for _ in range(4):
            h = await client.get("/api/v1/health/ready")
            assert h.status_code == 200
            h_json = h.json()
            assert h_json["vector_backend"] == "sqlite_json"
            assert h_json["task_execution_mode"] == "inline"
            assert "content-security-policy" in h.headers
            assert "x-request-id" in h.headers

        # General API requests succeed up to limit (2), then 3rd returns 429
        r1 = await client.get("/api/v1/overview", headers=MANAGER_HEADERS)
        assert r1.status_code == 200
        assert r1.headers["x-ratelimit-limit"] == "2"

        r2 = await client.get("/api/v1/overview", headers=MANAGER_HEADERS)
        assert r2.status_code == 200

        r3 = await client.get("/api/v1/overview", headers=MANAGER_HEADERS)
        assert r3.status_code == 429
        assert "retry-after" in r3.headers


@pytest.mark.asyncio
async def test_async_policy_upload_job_lifecycle(tmp_path: Path) -> None:
    test_app = make_test_app(tmp_path)
    pdf_bytes = build_minimal_pdf(
        [
            [
                "ACORD 140 COMMERCIAL PROPERTY DECLARATIONS",
                "Policy Number: POL-ASYNC-2026-101",
                "Named Insured: Async Harbor Terminal LLC",
                "Effective Date: 2026-01-01",
                "Expiration Date: 2027-01-01",
                "Per Occurrence Limit: $750,000",
                "Aggregate Limit: $1,500,000",
                "Deductible: $2,500",
            ],
            [
                "Coverage Grant (Section I.A): Terminal Property Coverage",
                "Covers terminal buildings and equipment up to $750,000.",
            ],
        ]
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Empty upload rejected cleanly
        bad = await client.post(
            "/api/v1/intake/policies/upload-async",
            headers=ADJUSTER_HEADERS,
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert bad.status_code == 400

        # Valid async upload queues and runs inline BackgroundTasks worker
        queued = await client.post(
            "/api/v1/intake/policies/upload-async",
            headers=ADJUSTER_HEADERS,
            files={"file": ("async_harbor.pdf", pdf_bytes, "application/pdf")},
        )
        assert queued.status_code == 202
        job = queued.json()
        assert job["filename"] == "async_harbor.pdf"

        # Wait briefly if needed and poll job status
        polled = await client.get(f"/api/v1/jobs/{job['id']}", headers=ADJUSTER_HEADERS)
        assert polled.status_code == 200
        job_state = polled.json()
        assert job_state["status"] == "completed"
        assert job_state["policy_id"] is not None
        assert job_state["result"]["policy_number"] == "POL-ASYNC-2026-101"

        jobs_list = await client.get("/api/v1/jobs", headers=ADJUSTER_HEADERS)
        assert jobs_list.status_code == 200
        assert any(item["id"] == job["id"] for item in jobs_list.json())


@pytest.mark.asyncio
async def test_concurrent_audit_sequencing_and_vector_helpers(tmp_path: Path) -> None:
    test_app = make_test_app(tmp_path)
    from app.db.session import ensure_db_initialized

    await ensure_db_initialized(test_app)
    actor = Actor(email="conc@test.local", role="claims_manager", auth_method="test")

    async def _append(idx: int) -> None:
        async with test_app.state.session_factory() as session:
            assert is_postgres_session(session) is False
            await record_audit_event(
                session,
                event_type="test.concurrent",
                actor=actor,
                entity_type="claim",
                entity_id=f"c-{idx}",
                action="checked",
                details={"idx": idx},
            )
            await session.commit()

    import asyncio

    await asyncio.gather(*(_append(i) for i in range(6)))

    async with test_app.state.session_factory() as session:
        check = await verify_audit_chain(session)
        assert check.valid is True
        assert check.total_events == 6

    literal = format_pgvector_literal([0.25, -0.5, 0.125])
    assert literal == "[0.250000,-0.500000,0.125000]"
    _ = Settings()
    _ = ThreadPoolExecutor


@pytest.mark.asyncio
async def test_llm_http_retry_recovers_from_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"response": "Recovered OK"}

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: object) -> FakeResp:
        nonlocal calls
        _ = (self, url, kwargs)
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("transient network hiccup")
        return FakeResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    data = await _post_with_retry("http://localhost:11434/api/generate", json={"prompt": "hi"})
    assert data["response"] == "Recovered OK"
    assert calls == 2
