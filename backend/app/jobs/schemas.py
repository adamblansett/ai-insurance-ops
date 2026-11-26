from datetime import datetime
from typing import Any

from pydantic import BaseModel


class IngestionJobOut(BaseModel):
    """Serialized asynchronous policy ingestion job status."""

    id: str
    job_type: str
    status: str
    filename: str
    policy_id: str | None
    requested_by: str
    progress_pct: int
    result: dict[str, Any]
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
