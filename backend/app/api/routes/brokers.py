from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.broker import BrokerAccount, BrokerName
from app.broker.factory import get_broker_adapter
from app.schemas.broker import (
    BrokerConnectRequest,
    BrokerAccountResponse,
    BrokerStatusResponse,
)

router = APIRouter()


@router.get("", response_model=List[BrokerAccountResponse])
async def list_broker_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all active broker accounts (migrating any legacy shoonya accounts to dhan)."""
    # Auto-migrate any legacy shoonya accounts to dhan
    try:
        await db.execute(
            update(BrokerAccount)
            .where(BrokerAccount.broker == BrokerName.shoonya)
            .values(broker=BrokerName.dhan)
        )
        await db.commit()
    except Exception:
        await db.rollback()

    result = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.user_id == current_user.id,
            BrokerAccount.broker != BrokerName.shoonya,
        )
    )
    return result.scalars().all()


@router.post("", response_model=BrokerAccountResponse, status_code=201)
async def connect_broker(
    payload: BrokerConnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Link a broker account to the user's profile."""
    existing = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.user_id == current_user.id,
            BrokerAccount.broker == payload.broker,
            BrokerAccount.client_id == payload.client_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Broker account already linked")

    from app.core.config import settings
    is_active = False
    if payload.broker == BrokerName.dhan and settings.DHAN_ACCESS_TOKEN:
        is_active = True

    account = BrokerAccount(
        user_id=current_user.id,
        broker=payload.broker,
        client_id=payload.client_id,
        paper_trading=payload.paper_trading,
        is_active=is_active,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.post("/{account_id}/activate", response_model=BrokerStatusResponse)
async def activate_broker(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Activate a broker account — paper activates immediately, live attempts real connection."""
    account = await _get_account(account_id, current_user.id, db)

    # Paper trading — just mark active, no credentials needed
    if account.paper_trading:
        account.is_active = True
        await db.commit()
        return BrokerStatusResponse(is_active=True, message="Paper account activated")

    broker_name = account.broker.value.upper()

    # Live trading — attempt real broker connection
    from app.core.config import settings
    try:
        from app.broker.dhan import DhanAdapter
        client_id = account.client_id or settings.DHAN_CLIENT_ID
        access_token = settings.DHAN_ACCESS_TOKEN
        if account.encrypted_access_token:
            from app.core.security import decrypt_broker_token
            try:
                access_token = decrypt_broker_token(account.encrypted_access_token)
            except Exception:
                pass
        adapter = DhanAdapter(client_id=client_id, access_token=access_token)
        success = await adapter.connect()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{broker_name} connection error: {e}")

    account.is_active = success
    await db.commit()

    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"{broker_name} login failed — check credentials in .env",
        )
    return BrokerStatusResponse(is_active=True, message=f"{broker_name} connected and verified successfully")


@router.delete("/{account_id}", status_code=204)
async def disconnect_broker(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a broker account safely, unlinking trades and removing child dependencies."""
    from app.services.broker_service import purge_broker_account

    account = await _get_account(account_id, current_user.id, db)
    await purge_broker_account(db, account)


@router.get("/{account_id}/positions")
async def get_positions(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch live positions from broker (or paper book)."""
    account = await _get_account(account_id, current_user.id, db)
    adapter = get_broker_adapter(account)
    if not account.paper_trading:
        await adapter.connect()
    return {"positions": await adapter.get_positions()}


@router.get("/{account_id}/funds")
async def get_funds(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch available funds / margin."""
    account = await _get_account(account_id, current_user.id, db)
    adapter = get_broker_adapter(account)
    if not account.paper_trading:
        await adapter.connect()
    return {"funds": await adapter.get_funds()}


@router.get("/{account_id}/orders")
async def get_orders(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch today's order book from broker."""
    account = await _get_account(account_id, current_user.id, db)
    adapter = get_broker_adapter(account)
    if not account.paper_trading:
        await adapter.connect()
    orders = adapter.api.get_order_book() or [] if hasattr(adapter, "api") else []
    return {"orders": orders}


async def _get_account(account_id: UUID, user_id, db: AsyncSession) -> BrokerAccount:
    result = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.id == account_id,
            BrokerAccount.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Broker account not found")
    return account


@router.patch("/{account_id}/deactivate")
async def deactivate_broker(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a broker account without removing it."""
    account = await _get_account(account_id, current_user.id, db)
    account.is_active = False
    await db.commit()
    return {"status": "deactivated", "id": str(account_id)}
