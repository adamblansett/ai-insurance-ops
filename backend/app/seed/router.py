from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Actor, require_roles
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.llm.router import LLMRouter, get_llm_router
from app.seed.demo_data import seed_demo_dataset

router = APIRouter(prefix="/seed", tags=["seed"])


class SeedDemoIn(BaseModel):
    """Demo dataset seed trigger options."""

    reset: bool = False


class SeedDemoOut(BaseModel):
    """Summary of demo dataset seeding operation."""

    status: str
    message: str
    policies: int
    claims: int = 0
    verifications: int = 0
    submissions: int = 0


@router.post("/demo", response_model=SeedDemoOut)
async def seed_demo_endpoint(
    payload: SeedDemoIn,
    request: Request,
    actor: Actor = Depends(require_roles("claims_manager", "admin")),
    db: AsyncSession = Depends(get_db),
    llm_router: LLMRouter = Depends(get_llm_router),
    settings: Settings = Depends(get_settings),
) -> SeedDemoOut:
    """Populate or reset realistic AI Insurance Operations demo data."""
    app_cfg = getattr(request.app.state, "settings", None)
    cfg = app_cfg if isinstance(app_cfg, Settings) else settings
    result = await seed_demo_dataset(
        db,
        llm_router=llm_router,
        settings=cfg,
        actor=actor,
        reset=payload.reset,
    )
    return SeedDemoOut(
        status=str(result.get("status", "ok")),
        message=str(result.get("message", "")),
        policies=int(result.get("policies", 0)),
        claims=int(result.get("claims", 0)),
        verifications=int(result.get("verifications", 0)),
        submissions=int(result.get("submissions", 0)),
    )
