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


class DhanTotpSetup(BaseModel):
    pin: str
    totp_secret: str


class BrokerCredentials(BaseModel):
    broker:       str   # "dhan"
    client_id:    str
    access_token: str
    paper_trading: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _sync_dhan_token_to_db(db: AsyncSession, new_token: str, client_id: Optional[str] = None):
    """Ensure the Dhan master account in PostgreSQL holds the active encrypted token."""
    from app.models.broker import BrokerAccount, BrokerName
    from app.core.security import encrypt_broker_token
    from sqlalchemy import select

    clean_token = new_token.strip()
    enc = encrypt_broker_token(clean_token)
    res = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.broker == BrokerName.dhan,
            BrokerAccount.is_active == True,
        )
    )
    accounts = res.scalars().all()
    updated_any = False
    for acc in accounts:
        if acc.account_role == "MASTER" or (client_id and acc.client_id == client_id) or not acc.client_id:
            acc.encrypted_access_token = enc
            if client_id and not acc.client_id:
                acc.client_id = client_id
            updated_any = True
    if updated_any:
        await db.commit()


def _update_env(key: str, value: str):
    """Update a key in every project .env that exists (repo root and backend/)."""
    from app.core.env_files import existing_env_files

    paths = existing_env_files()
    if not paths:
        return False
    for env_path in paths:
        with env_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        updated = []
        found = False
        for line in lines:
            if line.startswith(f"{key}="):
                updated.append(f"{key}={value}\n")
                found = True
            else:
                updated.append(line)
        if not found:
            updated.append(f"\n{key}={value}\n")
        with env_path.open("w", encoding="utf-8") as f:
            f.writelines(updated)
    return True


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
    db: AsyncSession = Depends(get_db),
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

    # Synchronize database BrokerAccount records
    await _sync_dhan_token_to_db(db, body.access_token, body.client_id)

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
    db: AsyncSession = Depends(get_db),
):
    """Update only the Dhan access token (quick daily refresh)."""
    _require_admin(current_user)
    from app.core.config import settings

    if not body.access_token.strip():
        raise HTTPException(status_code=400, detail="access_token required")

    clean_tok = body.access_token.strip()
    settings.DHAN_ACCESS_TOKEN = clean_tok
    _update_env("DHAN_ACCESS_TOKEN", clean_tok)

    # Synchronize database BrokerAccount records
    await _sync_dhan_token_to_db(db, clean_tok)

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


@router.post("/dhan-totp")
async def update_dhan_totp(
    body: DhanTotpSetup,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Configure Dhan PIN and TOTP secret and immediately generate fresh 24h access token."""
    _require_admin(current_user)
    from app.core.config import settings
    from app.broker.dhan_auth import get_auth_manager

    pin = body.pin.strip()
    totp_secret = body.totp_secret.strip().replace(" ", "").upper()
    if not pin or not totp_secret:
        raise HTTPException(status_code=400, detail="pin and totp_secret required")

    settings.DHAN_PIN = pin
    settings.DHAN_TOTP_SECRET = totp_secret
    _update_env("DHAN_PIN", pin)
    _update_env("DHAN_TOTP_SECRET", totp_secret)

    # Reset auth manager
    import app.broker.dhan_auth as auth_mod
    auth_mod._auth_manager = None

    # Immediately attempt generating fresh token via auth.dhan.co
    mgr = get_auth_manager()
    res = mgr.generate_token_totp()
    if not res:
        raise HTTPException(
            status_code=400,
            detail="Failed to generate Dhan token with provided PIN & TOTP Secret. Check that PIN is your 6-digit Dhan login PIN and TOTP secret is base32."
        )

    new_token = res["access_token"]
    mgr._apply_token(new_token)
    await _sync_dhan_token_to_db(db, new_token, mgr.client_id)

    return {
        "status": "totp_configured",
        "valid": True,
        "method": "totp",
        "expires_at": res.get("expires_at"),
    }


@router.post("/dhan-renew")
async def renew_dhan_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger automated token renewal (tries TOTP first if configured, otherwise calls RenewToken API)."""
    _require_admin(current_user)

    from app.core.config import settings
    from app.broker.dhan_auth import get_auth_manager
    mgr = get_auth_manager()

    result = None
    # 1. If TOTP credentials configured, generate a fresh token (works even if current is expired)
    if getattr(settings, "DHAN_PIN", "") and getattr(settings, "DHAN_TOTP_SECRET", ""):
        try:
            result = mgr.generate_token_totp()
        except Exception as e:
            logger.warning(f"TOTP token generation attempt error: {e}")

    # 2. Otherwise / fallback to RenewToken (extends existing active token)
    if not result:
        result = mgr.renew_token()

    if not result:
        raise HTTPException(
            status_code=400,
            detail=(
                "Token renewal failed: Dhan RenewToken only extends currently active (unexpired) tokens. "
                "If your token has expired, please paste a fresh token from web.dhan.co, "
                "or configure your 6-digit Dhan PIN and TOTP Authenticator Secret for automated generation."
            )
        )

    new_token = result["access_token"]
    mgr._apply_token(new_token)
    await _sync_dhan_token_to_db(db, new_token, mgr.client_id)

    return {
        "status": "renewed",
        "method": result.get("method", "renew"),
        "expires_at": result.get("expires_at"),
    }


@router.get("/status")
async def get_settings_status(current_user: User = Depends(get_current_user)):
    """Get overall platform settings status."""
    _require_admin(current_user)
    from app.core.config import settings
    from app.broker.dhan_auth import get_auth_manager

    mgr         = get_auth_manager()
    token_valid = mgr.is_token_valid()
    info        = mgr.get_token_expiry_info()

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
            "client_id_set":     bool(settings.DHAN_CLIENT_ID),
            "client_id":         mgr.client_id,
            "token_set":         bool(settings.DHAN_ACCESS_TOKEN),
            "token_valid":       token_valid,
            "totp_configured":   bool(getattr(settings, "DHAN_PIN", "") and getattr(settings, "DHAN_TOTP_SECRET", "")),
            "alert":             alert,
            "issued_at_ist":     info.get("issued_at_ist"),
            "expires_at_ist":    info.get("expires_at_ist"),
            "hours_remaining":   info.get("hours_remaining"),
            "seconds_remaining": info.get("seconds_remaining"),
            "is_expired":        info.get("is_expired"),
            "is_expiring_soon":  info.get("is_expiring_soon"),
            "is_jwt":            info.get("is_jwt"),
        },
        "celery": {
            "schedules": {
                "token_renewal":  "Every 30m (Proactive)",
                "csv_refresh":    "08:00 IST daily",
                "risk_reset":     "09:15 IST daily",
            }
        }
    }
