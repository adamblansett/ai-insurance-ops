from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Actor, get_current_actor
from app.db.models import IngestionJob
from app.db.session import get_db
from app.jobs.schemas import IngestionJobOut
from app.jobs.service import serialize_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[IngestionJobOut])
async def list_jobs(
    limit: int = Query(default=25, ge=1, le=100),
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[IngestionJobOut]:
    """List recent asynchronous policy ingestion jobs."""
    stmt = select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [serialize_job(row) for row in rows]


@router.get("/{job_id}", response_model=IngestionJobOut)
async def get_job(
    job_id: str,
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> IngestionJobOut:
    """Fetch status and result metadata for a single asynchronous ingestion job."""
    job = await db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion job '{job_id}' not found.",
        )
    return serialize_job(job)
