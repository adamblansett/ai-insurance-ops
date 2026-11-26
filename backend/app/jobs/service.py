import base64

import structlog
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import Actor
from app.core.config import Settings
from app.db.base import utcnow
from app.db.models import IngestionJob
from app.intake.service import ingest_uploaded_policy_file
from app.jobs.celery_app import get_celery_app
from app.jobs.schemas import IngestionJobOut
from app.llm.router import LLMRouter

logger = structlog.get_logger(__name__)


def serialize_job(job: IngestionJob) -> IngestionJobOut:
    return IngestionJobOut(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        filename=job.filename,
        policy_id=job.policy_id,
        requested_by=job.requested_by,
        progress_pct=job.progress_pct,
        result=job.result_json,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


async def create_ingestion_job(
    db: AsyncSession,
    *,
    filename: str,
    actor: Actor,
) -> IngestionJob:
    """Create and persist a queued ingestion job record."""
    job = IngestionJob(
        job_type="policy_upload",
        status="queued",
        filename=filename,
        requested_by=actor.email,
        progress_pct=0,
        result_json={},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def execute_ingestion_job(
    *,
    job_id: str,
    filename: str,
    data: bytes,
    actor: Actor,
    session_factory: async_sessionmaker[AsyncSession],
    llm_router: LLMRouter,
    settings: Settings,
) -> IngestionJob:
    """Execute background policy ingestion and persist completion or failure state."""
    async with session_factory() as session:
        job = await session.get(IngestionJob, job_id)
        if job is None:
            raise RuntimeError(f"Ingestion job '{job_id}' not found.")
        job.status = "running"
        job.progress_pct = 25
        job.started_at = utcnow()
        await session.commit()

        try:
            policy = await ingest_uploaded_policy_file(
                session,
                filename=filename,
                data=data,
                actor=actor,
                llm_router=llm_router,
                settings=settings,
            )
            job.status = "completed"
            job.progress_pct = 100
            job.policy_id = policy.id
            job.completed_at = utcnow()
            job.result_json = {
                "policy_id": policy.id,
                "policy_number": policy.policy_number,
                "clause_count": len(policy.clauses),
            }
            await session.commit()
            await session.refresh(job)
            return job
        except Exception as exc:
            await session.rollback()
            refreshed = await session.get(IngestionJob, job_id)
            if refreshed is None:
                raise
            refreshed.status = "failed"
            refreshed.progress_pct = 100
            refreshed.completed_at = utcnow()
            refreshed.error_message = str(exc)
            await session.commit()
            await session.refresh(refreshed)
            logger.warning("ingestion_job_failed", job_id=job_id, error=str(exc))
            return refreshed


def dispatch_policy_upload_job(
    *,
    background_tasks: BackgroundTasks,
    job_id: str,
    filename: str,
    data: bytes,
    actor: Actor,
    session_factory: async_sessionmaker[AsyncSession],
    llm_router: LLMRouter,
    settings: Settings,
) -> None:
    """Dispatch background policy upload via FastAPI BackgroundTasks or Celery."""
    if settings.task_execution_mode == "celery":
        celery_app = get_celery_app(settings)
        encoded = base64.b64encode(data).decode("ascii")
        celery_app.send_task(
            "app.jobs.ingest_policy_document",
            args=[job_id, filename, encoded, actor.email, actor.role],
        )
        return

    background_tasks.add_task(
        execute_ingestion_job,
        job_id=job_id,
        filename=filename,
        data=data,
        actor=actor,
        session_factory=session_factory,
        llm_router=llm_router,
        settings=settings,
    )
