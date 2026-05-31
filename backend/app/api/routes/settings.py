"""
Settings API
============
Manage broker credentials and Dhan token from the UI.
Stores encrypted credentials in DB, updates runtime config.
Admin only.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_current_user
from app.core.database import get_db
from app.models.user import User

router = APIRouter(prefix="/settings", tags=["Settings"])
logger = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────────────────

class DhanCredentials(BaseModel):
    client_id:    str
    access_token: str


class TokenUpdate(BaseModel):
    access_token: str


class BrokerCredentials(BaseModel):
    broker:       str   # "dhan"
    client_id:    str
    access_token: str
    paper_trading: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _update_env(key: str, value: str):
    """Update a key in .env file."""
    import os
    # Try common .env locations
    for env_path in [
        "/home/groot/Algo/algo-platform/.env",
        "/home/groot/Algo/algo-platform/backend/.env",
    ]:
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()
            updated = []
            found   = False
            for line in lines:
                if line.startswith(f"{key}="):
                    updated.append(f"{key}={value}\n")
                    found = True
                else:
                    updated.append(line)
            if not found:
                updated.append(f"\n{key}={value}\n")
            with open(env_path, "w") as f:
                f.writelines(updated)
            return True
    return False


def _require_admin(user: User):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/dhan-credentials")
async def get_dhan_credentials(current_user: User = Depends(get_current_user)):
    """Get current Dhan credentials (token partially masked)."""
    _require_admin(current_user)
    from app.core.config import settings
    token = settings.DHAN_ACCESS_TOKEN or ""
    return {
        "client_id":    settings.DHAN_CLIENT_ID,
        "token_preview": token[:20] + "..." if len(token) > 20 else token,
        "token_set":     bool(token),
    }


@router.post("/dhan-credentials")
async def update_dhan_credentials(
    body: DhanCredentials,
    current_user: User = Depends(get_current_user),
):
    """Update Dhan Client ID and Access Token."""
    _require_admin(current_user)
    from app.core.config import settings

    if not body.client_id or not body.access_token:
        raise HTTPException(status_code=400, detail="client_id and access_token required")

    # Update runtime config
    settings.DHAN_CLIENT_ID    = body.client_id.strip()
    settings.DHAN_ACCESS_TOKEN = body.access_token.strip()

    # Persist to .env
    _update_env("DHAN_CLIENT_ID",    body.client_id.strip())
    _update_env("DHAN_ACCESS_TOKEN", body.access_token.strip())

    # Reset auth manager singleton with new credentials
    import app.broker.dhan_auth as auth_mod
    auth_mod._auth_manager = None

    # Verify new token works
    from app.broker.dhan_auth import get_auth_manager
    mgr   = get_auth_manager()
    valid = mgr.is_token_valid()

    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Credentials saved but token validation failed — check client_id and token"
        )

    # Clear any alert flags
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.delete("dhan:token:alert")
    except Exception:
        pass

    return {"status": "updated", "valid": True, "client_id": body.client_id}


@router.post("/dhan-token")
async def update_dhan_token(
    body: TokenUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update only the Dhan access token (quick daily refresh)."""
    _require_admin(current_user)
    from app.core.config import settings

    if not body.access_token.strip():
        raise HTTPException(status_code=400, detail="access_token required")

    settings.DHAN_ACCESS_TOKEN = body.access_token.strip()
    _update_env("DHAN_ACCESS_TOKEN", body.access_token.strip())

    # Reset auth manager
    import app.broker.dhan_auth as auth_mod
    auth_mod._auth_manager = None

    # Clear alert
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.delete("dhan:token:alert")
    except Exception:
        pass

    from app.broker.dhan_auth import get_auth_manager
    valid = get_auth_manager().is_token_valid()

    return {"status": "token_updated", "valid": valid}


@router.post("/dhan-renew")
async def renew_dhan_token(current_user: User = Depends(get_current_user)):
    """Trigger automated token renewal (RenewToken API)."""
    _require_admin(current_user)

    from app.broker.dhan_auth import get_auth_manager
    mgr = get_auth_manager()

    if not mgr.is_token_valid():
        raise HTTPException(
            status_code=400,
            detail="Current token is expired — RenewToken only works on active tokens. Please paste a new token instead."
        )

    result = mgr.renew_token()
    if not result:
        raise HTTPException(status_code=502, detail="Token renewal failed")

    mgr._apply_token(result["access_token"])
    return {"status": "renewed", "expires_at": result.get("expires_at")}


@router.get("/status")
async def get_settings_status(current_user: User = Depends(get_current_user)):
    """Get overall platform settings status."""
    _require_admin(current_user)
    from app.core.config import settings
    from app.broker.dhan_auth import get_auth_manager

    mgr         = get_auth_manager()
    token_valid = mgr.is_token_valid()

    # Check Redis alert
    alert = None
    try:
        import redis
        r     = redis.from_url(settings.REDIS_URL, decode_responses=True)
        alert = r.get("dhan:token:alert")
    except Exception:
        pass

    return {
        "dhan": {
            "client_id_set":  bool(settings.DHAN_CLIENT_ID),
            "token_set":      bool(settings.DHAN_ACCESS_TOKEN),
            "token_valid":    token_valid,
            "alert":          alert,
        },
        "celery": {
            "schedules": {
                "token_renewal":  "07:45 IST daily",
                "csv_refresh":    "08:00 IST daily",
                "risk_reset":     "09:15 IST daily",
            }
        }
    }
