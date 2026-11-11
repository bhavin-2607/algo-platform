from fastapi import APIRouter, Depends, HTTPException, status
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


@router.post("/register", status_code=403)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=403, detail="Accounts are created by an admin")


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.mfa_enabled:
        if not payload.mfa_token:
            raise HTTPException(
                status_code=200,
                detail="MFA token required",
                headers={"X-MFA-Required": "true"},
            )
        if not verify_mfa_token(user.mfa_secret, payload.mfa_token):
            raise HTTPException(status_code=401, detail="Invalid MFA token")

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
