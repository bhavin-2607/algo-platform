"""
Dhan Token Management API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_current_user
from app.core.database import get_db
from app.models.user import User

router = APIRouter(prefix="/dhan-auth", tags=["dhan-auth"])


@router.get("/token-status")
async def token_status(current_user: User = Depends(get_current_user)):
    """Check token health — available to all users for UI banner."""
    from app.broker.dhan_auth import get_auth_manager
    from app.core.config import settings
    import redis

    mgr   = get_auth_manager()
    valid = mgr.is_token_valid()
    info  = mgr.get_token_expiry_info()

    # Check Redis for alert flag
    alert = None
    try:
        r     = redis.from_url(settings.REDIS_URL, decode_responses=True)
        alert = r.get("dhan:token:alert")
        expires = r.get("dhan:token:expires")
    except Exception:
        expires = None

    return {
        "valid":             valid,
        "alert":             alert,
        "expires_at":        info.get("expires_at_ist") or expires,
        "expires_at_ist":    info.get("expires_at_ist"),
        "issued_at_ist":     info.get("issued_at_ist"),
        "hours_remaining":   info.get("hours_remaining"),
        "seconds_remaining": info.get("seconds_remaining"),
        "is_expired":        info.get("is_expired"),
        "is_expiring_soon":  info.get("is_expiring_soon"),
        "client_id":         mgr.client_id,
        "totp_configured":   bool(
            getattr(settings, "DHAN_PIN", "") and
            getattr(settings, "DHAN_TOTP_SECRET", "")
        ),
    }


@router.post("/renew-token")
async def renew_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger token renewal — admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from app.broker.dhan_auth import get_auth_manager
    from app.api.routes.settings import _sync_dhan_token_to_db

    mgr    = get_auth_manager()
    result = mgr.auto_renew(max_retries=1)

    if not result:
        raise HTTPException(
            status_code=502,
            detail="Token renewal failed: RenewToken requires an active token, or configure Dhan PIN & TOTP. Use /manual-token to paste a new token."
        )

    await _sync_dhan_token_to_db(db, result["access_token"], mgr.client_id)
    return {"status": "renewed", "method": result["method"], "expires_at": result.get("expires_at")}


class ManualTokenInput(BaseModel):
    access_token: str


@router.post("/manual-token")
async def set_manual_token(
    body: ManualTokenInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually set a new Dhan access token.
    Use this when automated renewal fails:
      1. Go to web.dhan.co → My Profile → Access DhanHQ APIs
      2. Generate new token
      3. POST here with the new token
    Admin only.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from app.broker.dhan_auth import get_auth_manager
    from app.api.routes.settings import _sync_dhan_token_to_db
    from app.core.config import settings
    import redis

    new_token = body.access_token.strip()
    mgr = get_auth_manager()
    mgr._apply_token(new_token)
    mgr._set_token_status("ok")
    await _sync_dhan_token_to_db(db, new_token, mgr.client_id)

    # Clear alert flag
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.delete("dhan:token:alert")
    except Exception:
        pass

    # Verify new token works
    valid = mgr.is_token_valid()
    if not valid:
        raise HTTPException(status_code=400, detail="Token applied but validation failed — check token is correct")

    return {"status": "token_updated", "valid": True}
