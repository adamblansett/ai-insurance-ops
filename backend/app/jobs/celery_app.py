import asyncio
import base64
from typing import Any

from app.core.auth import Actor
from app.core.config import Settings, get_settings
from app.db.session import build_engine, build_session_factory
from app.llm.router import LLMRouter

_CELERY_APP: Any = None


def get_celery_app(settings: Settings | None = None) -> Any:
    """Lazily construct a Celery application when worker dependencies are installed."""
    global _CELERY_APP
    if _CELERY_APP is not None:
        return _CELERY_APP

    try:
        from celery import Celery
    except ImportError as exc:
        raise RuntimeError(
            "Celery worker extra is not installed. Run `pip install -e '.[worker]'` "
            "or set TASK_EXECUTION_MODE=inline."
        ) from exc

    cfg = settings or get_settings()
    app = Celery(
        "ai_insurance_ops",
        broker=cfg.celery_broker_url,
        backend=cfg.celery_result_backend,
    )
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"
    app.conf.accept_content = ["json"]

    @app.task(name="app.jobs.ingest_policy_document")
    def ingest_policy_document_task(
        job_id: str,
        filename: str,
        data_b64: str,
        actor_email: str,
        actor_role: str,
    ) -> dict[str, Any]:
        from app.jobs.service import execute_ingestion_job

        raw_bytes = base64.b64decode(data_b64.encode("ascii"))
        actor = Actor(
            email=actor_email,
            role=actor_role,  # type: ignore[arg-type]
            auth_method="celery_worker",
        )
        engine = build_engine(cfg.database_url)
        session_factory = build_session_factory(engine)
        llm_router = LLMRouter(cfg)

        async def _run() -> dict[str, Any]:
            try:
                job = await execute_ingestion_job(
                    job_id=job_id,
                    filename=filename,
                    data=raw_bytes,
                    actor=actor,
                    session_factory=session_factory,
                    llm_router=llm_router,
                    settings=cfg,
                )
                return {"job_id": job.id, "status": job.status, "policy_id": job.policy_id}
            finally:
                await engine.dispose()

        return asyncio.run(_run())

    _CELERY_APP = app
    return app
