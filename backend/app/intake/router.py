from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import Actor, get_current_actor, require_roles
from app.core.config import Settings, get_settings
from app.db.models import Policy, PolicyClause
from app.db.session import get_db
from app.intake.schemas import (
    ClauseSearchIn,
    ClauseSearchResultOut,
    PolicyClauseOut,
    PolicyCreateIn,
    PolicyDetailOut,
    PolicySummaryOut,
)
from app.intake.service import (
    create_policy_structured,
    ingest_uploaded_policy_file,
    list_policies_with_counts,
    search_clauses_hybrid,
    serialize_clause,
    serialize_policy_detail,
)
from app.jobs.schemas import IngestionJobOut
from app.jobs.service import (
    create_ingestion_job,
    dispatch_policy_upload_job,
    serialize_job,
)
from app.llm.router import LLMRouter, get_llm_router

router = APIRouter(prefix="/intake", tags=["intake"])

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024
_ALLOWED_EXTENSIONS = (".pdf", ".txt", ".json")


def _resolve_settings(request: Request, fallback: Settings) -> Settings:
    app_cfg = getattr(request.app.state, "settings", None)
    return app_cfg if isinstance(app_cfg, Settings) else fallback


@router.post("/policies", response_model=PolicyDetailOut, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: PolicyCreateIn,
    request: Request,
    actor: Actor = Depends(require_roles("adjuster", "underwriter", "claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    settings: Settings = Depends(get_settings),
) -> PolicyDetailOut:
    """Ingest a structured policy declaration and index its clauses."""
    cfg = _resolve_settings(request, settings)
    policy = await create_policy_structured(
        db,
        payload=payload,
        actor=actor,
        llm_router=llm_router,
        settings=cfg,
    )
    return serialize_policy_detail(policy)


@router.post(
    "/policies/upload",
    response_model=PolicyDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_policy_document(
    request: Request,
    file: UploadFile = File(...),
    actor: Actor = Depends(require_roles("adjuster", "underwriter", "claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    settings: Settings = Depends(get_settings),
) -> PolicyDetailOut:
    """Parse an uploaded ACORD/policy PDF, TXT, or JSON file and index page-cited clauses."""
    filename = (file.filename or "").strip()
    if not filename or not filename.lower().endswith(_ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Upload a .pdf, .txt, or .json policy document.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Uploaded policy document exceeds the 15 MB size limit.",
        )

    cfg = _resolve_settings(request, settings)
    policy = await ingest_uploaded_policy_file(
        db,
        filename=filename,
        data=data,
        actor=actor,
        llm_router=llm_router,
        settings=cfg,
    )
    return serialize_policy_detail(policy)


@router.post(
    "/policies/upload-async",
    response_model=IngestionJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_policy_document_async(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    actor: Actor = Depends(require_roles("adjuster", "underwriter", "claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    settings: Settings = Depends(get_settings),
) -> IngestionJobOut:
    """Queue a policy PDF/TXT/JSON upload for asynchronous ingestion and indexing."""
    filename = (file.filename or "").strip()
    if not filename or not filename.lower().endswith(_ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Upload a .pdf, .txt, or .json policy document.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Uploaded policy document exceeds the 15 MB size limit.",
        )

    cfg = _resolve_settings(request, settings)
    job = await create_ingestion_job(db, filename=filename, actor=actor)
    dispatch_policy_upload_job(
        background_tasks=background_tasks,
        job_id=job.id,
        filename=filename,
        data=data,
        actor=actor,
        session_factory=request.app.state.session_factory,
        llm_router=llm_router,
        settings=cfg,
    )
    return serialize_job(job)


@router.get("/policies", response_model=list[PolicySummaryOut])
async def list_policies(
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PolicySummaryOut]:
    """List ingested policies with clause counts."""
    return await list_policies_with_counts(db)


@router.get("/policies/{policy_id}", response_model=PolicyDetailOut)
async def get_policy(
    policy_id: str,
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> PolicyDetailOut:
    """Retrieve a policy declaration with schedules and indexed clauses."""
    policy = (
        await db.execute(
            select(Policy).options(selectinload(Policy.clauses)).where(Policy.id == policy_id)
        )
    ).scalar_one_or_none()
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{policy_id}' not found.",
        )
    return serialize_policy_detail(policy)


@router.get("/policies/{policy_id}/clauses", response_model=list[PolicyClauseOut])
async def list_policy_clauses(
    policy_id: str,
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PolicyClauseOut]:
    """List all indexed clauses for a given policy ordered by page and section."""
    policy = await db.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{policy_id}' not found.",
        )
    stmt = (
        select(PolicyClause)
        .where(PolicyClause.policy_id == policy_id)
        .order_by(PolicyClause.page_number.asc(), PolicyClause.section_ref.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [serialize_clause(row) for row in rows]


@router.post("/clauses/search", response_model=list[ClauseSearchResultOut])
async def search_clauses(
    payload: ClauseSearchIn,
    request: Request,
    _: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[ClauseSearchResultOut]:
    """Perform hybrid vector + keyword search over indexed policy clauses."""
    cfg = _resolve_settings(request, settings)
    return await search_clauses_hybrid(
        db,
        query=payload.query,
        policy_id=payload.policy_id,
        clause_type=payload.clause_type,
        limit=payload.limit,
        settings=cfg,
    )
