"""Phase 2: ingestion_jobs table and PostgreSQL pgvector HNSW index.

Revision ID: 0002_phase2_pgvector_and_jobs
Revises: 0001_initial_schema
Create Date: 2026-11-26 07:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase2_pgvector_and_jobs"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("policy_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])
    op.create_index("ix_ingestion_jobs_policy_id", "ingestion_jobs", ["policy_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        op.execute(
            sa.text(
                "ALTER TABLE policy_clauses ADD COLUMN IF NOT EXISTS embedding_vec vector(384)"
            )
        )
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_policy_clauses_embedding_vec "
                "ON policy_clauses USING hnsw (embedding_vec vector_cosine_ops)"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP INDEX IF EXISTS ix_policy_clauses_embedding_vec"))
        op.execute(sa.text("ALTER TABLE policy_clauses DROP COLUMN IF EXISTS embedding_vec"))

    op.drop_index("ix_ingestion_jobs_policy_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
