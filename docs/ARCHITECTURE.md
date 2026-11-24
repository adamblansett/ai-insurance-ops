# AI Insurance Operations — Architecture Blueprint

## Overview

Open-source, self-hosted AI insurance operations platform for policy intake, claims triage, coverage verification, and underwriting support workflows.

This starter repository establishes the production baseline (typed configuration, security headers, health endpoints, CI checks, and Docker Compose topology) so domain features can be implemented cleanly without re-scaffolding infrastructure.

## Planned Domain Modules (`backend/app/`)

- `intake/` — Policy PDF/declaration parser with endorsement and schedule extraction
- `claims/` — FNOL intake pipeline, reserve-band triage, and adjuster queue routing
- `coverage/` — Clause-level coverage & exclusion matcher with page/section citations
- `underwriting/` — Loss-run analyzer and human-reviewed risk summary generator

## Security & Operational Invariants

1. **Fail-Fast Production Validation:** `validate_production_security()` refuses startup in `APP_ENV=production` if default dev secrets or wildcard CORS origins remain active.
2. **Cloud PII Redaction:** Outbound cloud LLM adapters run PII scrubbing when `LLM_REDACT_PII_FOR_CLOUD=true`.
3. **Human-in-the-Loop Approvals:** High-impact external writes (emails, accounting entries, identity changes, record merges) require explicit review states and immutable audit trails.
4. **Non-Root Containers:** Both the FastAPI API image and Nginx frontend image run as non-root users with `/api/v1/health/live` and `/api/v1/health/ready` probes.
