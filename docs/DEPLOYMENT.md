# Deployment & Operations Guide — AI Insurance Operations

## 1. Self-Hosted Docker Compose (Full Stack + `pgvector` + Redis + Optional Worker)

Start PostgreSQL (`pgvector/pgvector:pg16`), Redis, FastAPI API, and Nginx frontend:

```bash
docker compose up --build
```

- **Frontend UI:** `http://localhost:3000`
- **FastAPI & OpenAPI:** `http://localhost:8000/docs`
- **Health Probes:** `GET /api/v1/health/live` and `GET /api/v1/health/ready`

### Optional Profiles

- **Local Open-Weights LLM (Ollama):**
  ```bash
  docker compose --profile ollama up --build
  ```
- **Distributed Celery Background Ingestion Worker:**
  ```bash
  TASK_EXECUTION_MODE=celery docker compose --profile worker up --build
  ```

---

## 2. Database Migrations (`pgvector` & `ingestion_jobs`)

Run Alembic migrations against PostgreSQL (`DATABASE_URL=postgresql+asyncpg://...`):

```bash
cd backend
alembic upgrade head
```

- `0001_initial_schema`: Creates the 7 core operational tables (`policies`, `policy_clauses`, `claims`, `coverage_verifications`, `underwriting_submissions`, `approval_requests`, `audit_events`).
- `0002_phase2_pgvector_and_jobs`: Creates `ingestion_jobs`, enables the `vector` extension on PostgreSQL, adds `policy_clauses.embedding_vec vector(384)`, and creates an HNSW cosine index (`ix_policy_clauses_embedding_vec`).

On SQLite dev/test environments, migrations apply the relational tables cleanly and clause similarity falls back seamlessly to in-Python cosine similarity.

---

## 3. Production Security Checklist

Set the following environment variables before deploying (`APP_ENV=production`):

1. **`APP_ENV=production`** — Enables `Strict-Transport-Security`, disables `/api/v1/auth/token`, and enforces `validate_production_security()` fail-fast checks.
2. **`AUTH_SECRET_KEY`** — Unique random >= 32-byte HS256 signing secret (startup refuses the default dev secret).
3. **`AUTH_REQUIRE_TOKEN=true`** — Disables development `X-Actor-*` header impersonation and requires signed `Authorization: Bearer <jwt>` tokens on all non-health routes.
4. **`CORS_ORIGINS`** — Explicit comma-separated origin allowlist (wildcards `*` are rejected at startup).
5. **`LLM_REDACT_PII_FOR_CLOUD=true`** — Ensures outbound cloud Gemini prompts scrub SSN, FEIN, DOB, Driver's License, VIN, Member ID, Email, Phone, and Luhn payment cards before egress.
6. **`RATE_LIMIT_ENABLED=true`** — Enforces sliding-window throttling (`RATE_LIMIT_REQUESTS_PER_MINUTE=120`, `RATE_LIMIT_AUTH_PER_MINUTE=30`).

---

## 4. Cloud Run / Managed Container Deployment

1. Build and push `backend/Dockerfile` (`PORT=8000`, non-root `appuser`, `HEALTHCHECK` on `/api/v1/health/live`) and `frontend/Dockerfile` (unprivileged Nginx listening on `8080`).
2. Provision managed PostgreSQL 16+ with `pgvector` enabled and run `alembic upgrade head` as a pre-deploy migration job (`AUTO_CREATE_TABLES=false`, `SEED_DEMO_DATA=false`).
3. Configure Cloud Run readiness/startup probes against `/api/v1/health/ready` and `/api/v1/health/live`.
4. Store `AUTH_SECRET_KEY`, `DATABASE_URL`, and optional `GEMINI_API_KEY` in Secret Manager rather than plaintext env files.
