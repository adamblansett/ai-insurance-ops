from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import Actor, ActorRole, create_access_token, get_current_actor
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    """Request payload for issuing a development/test HS256 bearer token."""

    email: str = Field(min_length=3, max_length=255)
    role: ActorRole = "claims_manager"
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class TokenResponse(BaseModel):
    """Signed bearer token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: ActorRole
    email: str


@router.post("/token", response_model=TokenResponse)
async def issue_dev_token(
    payload: TokenRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Issue an HMAC-SHA256 bearer token in non-production environments."""
    app_cfg = getattr(request.app.state, "settings", None)
    cfg = app_cfg if isinstance(app_cfg, Settings) else settings
    if cfg.app_env.strip().lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-service token issuance is disabled in production.",
        )

    token = create_access_token(
        email=payload.email.strip(),
        role=payload.role,
        secret_key=cfg.auth_secret_key,
        ttl_seconds=payload.ttl_seconds,
    )
    return TokenResponse(
        access_token=token,
        expires_in=payload.ttl_seconds,
        role=payload.role,
        email=payload.email.strip(),
    )


@router.get("/me", response_model=Actor)
async def read_current_actor(actor: Actor = Depends(get_current_actor)) -> Actor:
    """Return the authenticated or development-header actor identity."""
    return actor
