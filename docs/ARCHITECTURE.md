# AI Insurance Operations — Architecture Blueprint

**Status:** Phase 1 Implemented

## Overview

Open-source, self-hosted AI insurance operations platform for policy intake, claims triage, coverage verification, and underwriting support workflows.

## Domain Modules (`backend/app/`)

- `intake/` — Policy PDF/TXT/JSON ACORD & declaration parser, deterministic hashed embeddings, schedule extraction, and hybrid clause search (`/api/v1/intake`).
- `claims/` — FNOL intake pipeline, reserve-band & LAE sizing, weighted SIU fraud red-flag scoring, and adjuster queue routing (`/api/v1/claims`).
- `coverage/` — Citation-grounded coverage matcher resolving policy effective windows, grants, endorsement buy-backs, sublimits, deductibles, notice conditions, and exclusions (`/api/v1/coverage`).
- `underwriting/` — LOB submission completeness scorer, 3/5-year loss-run & loss-ratio analyzer, risk-tier pricing engine, and supplemental reanalysis (`/api/v1/underwriting`).
- `audit/` — HITL approval gate engine and SHA-256 hash-chained immutable audit ledger with chain integrity verification and cloud PII/PHI redaction preview (`/api/v1/audit`).
- `llm/` — Local-first `LLMRouter` (`mock`, `ollama`, `gemini`) with automatic outbound PII/PHI scrubbing (`SSN`, `FEIN`, `DOB`, `Driver's License`, `VIN`, `Member ID`, `Email`, `Phone`, `Luhn Payment Card`).
- `seed/` — Idempotent demo dataset seeder (`POST /api/v1/seed/demo`) loading 3 policies (13 clauses), 4 FNOL claims, 4 coverage verifications, and 3 underwriting submissions.

## RBAC Matrix & Human-in-the-Loop (HITL) Boundaries

| Role | Read All | Policy Intake / Claims / Coverage Write | Underwriting Write | Decide `underwriting_decision` | Decide `claim_reserve` / `siu_referral` / `coverage_determination` | Seed / Reset Demo |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| `viewer` | Yes | No | No | No | No | No |
| `adjuster` | Yes | Yes | No | No | No | No |
| `underwriter` | Yes | Intake only | Yes | Yes | No | No |
| `claims_manager` | Yes | Yes | Yes | Yes | Yes | Yes |
| `admin` | Yes | Yes | Yes | Yes | Yes | Yes |

### Automatic HITL Triggers

- `claim_reserve`: Triggered when `recommended_reserve >= RESERVE_AUTO_APPROVE_LIMIT` (default `$25,000`).
- `siu_referral`: Triggered when `fraud_score >= FRAUD_SIU_THRESHOLD` (default `0.60`).
- `coverage_determination`: Triggered for `excluded`, `reservation_of_rights`, `policy_inactive`, or payouts `>= COVERAGE_AUTO_APPROVE_LIMIT` (default `$25,000`).
- `underwriting_decision`: Triggered when `recommended_action != "quote"` or `requested_limit >= UW_AUTO_QUOTE_LIMIT` (default `$1,000,000`).

## Security & Operational Invariants

1. **Fail-Fast Production Validation:** `validate_production_security()` refuses startup in `APP_ENV=production` if default dev secrets or wildcard CORS origins remain active, and `/api/v1/auth/token` is disabled in production.
2. **Cloud PII/PHI Redaction:** Outbound cloud LLM adapters run `redact_pii()` when `LLM_REDACT_PII_FOR_CLOUD=true`.
3. **Immutable Audit Chain:** Every state-changing action appends a SHA-256 hash-chained `audit_events` row verifiable via `GET /api/v1/audit/events/verify`.
4. **Non-Root Containers:** Both the FastAPI API image and Nginx frontend image run as non-root users with `/api/v1/health/live` and `/api/v1/health/ready` probes.
