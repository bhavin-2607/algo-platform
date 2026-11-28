from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import pyotp

from app.core.database import get_db
from app.core.security import (
    verify_password,
    create_access_token, create_refresh_token, decode_token,
    generate_mfa_secret, verify_mfa_token,
)
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    LoginRequest, RegisterRequest, RefreshRequest, TokenResponse,
    MFASetupResponse, MFAVerifyRequest,
)

router = APIRouter()


async def _check_login_rate_limit(client_ip: str) -> None:
    """Throttle brute-force login attempts (max 10 failed attempts per minute per IP)."""
    key = f"rate_limit:login_fails:{client_ip}"
    try:
        from app.core.redis_client import get_redis
        redis = get_redis()
        fails = await redis.get(key)
        if fails and int(fails) >= 10:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please wait 1 minute before trying again.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Gracefully fall through if Redis is unavailable


async def _record_login_failure(client_ip: str) -> None:
    key = f"rate_limit:login_fails:{client_ip}"
    try:
        from app.core.redis_client import get_redis
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
    except Exception:
        pass


async def _clear_login_failures(client_ip: str) -> None:
    key = f"rate_limit:login_fails:{client_ip}"
    try:
        from app.core.redis_client import get_redis
        redis = get_redis()
        await redis.delete(key)
    except Exception:
        pass


@router.post("/register", status_code=403)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=403, detail="Accounts are created by an admin")


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    client_ip = "127.0.0.1"
    if request:
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "127.0.0.1")
        )
    await _check_login_rate_limit(client_ip)

    identifier = (payload.username or payload.email or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Username or email is required")

    result = await db.execute(
        select(User).where(
            (User.username.ilike(identifier)) | (User.email.ilike(identifier))
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        await _record_login_failure(client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    if user.mfa_enabled:
        if not payload.mfa_token:
            raise HTTPException(
                status_code=200,
                detail="MFA token required",
                headers={"X-MFA-Required": "true"},
            )
        if not verify_mfa_token(user.mfa_secret, payload.mfa_token):
            await _record_login_failure(client_ip)
            raise HTTPException(status_code=401, detail="Invalid MFA token")

    await _clear_login_failures(client_ip)
    token_data = {"sub": str(user.id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Issue a new access token from a valid refresh token. Active use does not require a new login."""
    try:
        data = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if data.get("type") != "refresh" or not data.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    result = await db.execute(select(User).where(User.id == data["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    token_data = {"sub": str(user.id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secret = generate_mfa_secret()
    current_user.mfa_secret = secret
    await db.commit()

    totp = pyotp.TOTP(secret)
    qr_uri = totp.provisioning_uri(name=current_user.email, issuer_name="AlgoTradingPlatform")
    return MFASetupResponse(secret=secret, qr_uri=qr_uri)


@router.post("/mfa/verify")
async def mfa_verify(
    payload: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_mfa_token(current_user.mfa_secret, payload.token):
        raise HTTPException(status_code=400, detail="Invalid MFA token")
    current_user.mfa_enabled = True
    await db.commit()
    return {"message": "MFA enabled"}
