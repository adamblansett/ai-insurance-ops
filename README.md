# AI Insurance Operations

> Open-source, self-hosted AI insurance operations platform for policy intake, claims triage, coverage verification, and underwriting support workflows.

**Roadmap Stage:** Phase 1 — Core Professional & Enterprise Operations · **Status:** Phase 1 Implemented

## Core Capabilities

- **Policy Intake (`/api/v1/intake`):** Structured ACORD/declaration PDF, TXT, and JSON parsing, schedule extraction, page-numbered clause indexing, and hybrid vector + keyword clause search.
- **Claims Triage (`/api/v1/claims`):** FNOL normalization, severity tiering, reserve-band sizing, weighted SIU fraud indicator scoring, and adjuster queue routing (`fast_track_desk`, `field_property`, `complex_casualty`, `cyber_incident`, `siu_investigation`).
- **Coverage Verification (`/api/v1/coverage`):** Citation-grounded (`Policy · Page N · Section`) coverage grants, endorsement buy-backs, sublimits, deductibles, condition notice checks, and exclusions matching against claim facts.
- **Underwriting Support (`/api/v1/underwriting`):** LOB-specific submission completeness checklists, 3/5-year loss-run aggregation & loss-ratio calculation, composite risk scoring, indicated premium calculation, and senior UW escalation.
- **HITL Approvals & Cryptographic Audit (`/api/v1/audit`):** Role-scoped approval gates (`claim_reserve`, `siu_referral`, `coverage_determination`, `underwriting_decision`), SHA-256 hash-chained audit ledger with tamper verification, and outbound PII/PHI redaction sandbox (SSN, FEIN, DOB, Driver's License, VIN, Member ID, Email, Phone, and Luhn payment cards).

## Architecture & Engineering Standards

- **Backend (`backend/`):** Python 3.12+, FastAPI, Pydantic v2, async SQLAlchemy 2.0 (SQLite dev/CI & PostgreSQL `pgvector` production), Alembic migrations (`backend/alembic/`), HS256 JWT + RBAC (`viewer`, `adjuster`, `underwriter`, `claims_manager`, `admin`), ASGI security headers, and `/api/v1/health/{live,ready}` probes.
- **Frontend (`frontend/`):** React 18, TypeScript, Vite, Tailwind CSS, and Vitest + Testing Library console served behind unprivileged Nginx in production.
- **Privacy & AI Guardrails:** Offline deterministic `mock` mode for CI/dev, local-first Ollama support, and cloud Gemini PII/PHI scrubbing (`LLM_REDACT_PII_FOR_CLOUD=true`).
- **Containers & CI (`.github/workflows/ci.yml`):** Multi-stage Dockerfiles, PostgreSQL (`pgvector`) + Redis Compose topology, Ruff + Mypy + Pytest checks, TypeScript + Vitest + Vite build, `npm audit`, and Trivy filesystem scanning.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module details, RBAC matrix, and HITL boundaries.

## Quickstart

### Backend (Local Dev & Tests)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
SEED_DEMO_DATA=true uvicorn app.main:app --reload --port 8000
```

Run database migrations manually (optional when `AUTO_CREATE_TABLES=true`):

```bash
alembic upgrade head
```

Verify lint, types, and tests:

```bash
ruff check app tests
mypy app
pytest -v
```

### Frontend (Local Dev & Tests)

```bash
cd frontend
npm ci
npm run dev
```

Verify typecheck, unit tests, and production bundle:

```bash
npx tsc --noEmit
npm run test
npm run build
```

### Docker Compose

```bash
docker compose up --build
```

- Frontend UI: `http://localhost:3000`
- Backend API & OpenAPI Docs: `http://localhost:8000/docs`

---

## License

Licensed under the [MIT License](LICENSE).
