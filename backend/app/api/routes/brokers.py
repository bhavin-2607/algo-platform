from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.broker import BrokerAccount
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
    """Return all broker accounts linked to the current user."""
    result = await db.execute(
        select(BrokerAccount).where(BrokerAccount.user_id == current_user.id)
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

    account = BrokerAccount(
        user_id=current_user.id,
        broker=payload.broker,
        client_id=payload.client_id,
        paper_trading=payload.paper_trading,
        is_active=False,
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
    try:
        adapter = get_broker_adapter(account)
        success = await adapter.connect()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{broker_name} connection error: {e}")

    account.is_active = success
    await db.commit()

    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"{broker_name} login failed — check credentials in .env",
        )
    return BrokerStatusResponse(is_active=True, message=f"{broker_name} connected successfully")


@router.delete("/{account_id}", status_code=204)
async def disconnect_broker(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a broker account — also removes linked strategy assignments."""
    from sqlalchemy import select as sel
    from app.models.strategy import UserStrategyMap

    account = await _get_account(account_id, current_user.id, db)

    # Remove linked strategy maps first to avoid FK violation
    result = await db.execute(
        sel(UserStrategyMap).where(UserStrategyMap.broker_account_id == account_id)
    )
    maps = result.scalars().all()
    for m in maps:
        await db.delete(m)

    await db.delete(account)
    await db.commit()


@router.get("/{account_id}/positions")
async def get_positions(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch live positions from Shoonya (or paper book)."""
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
    """Fetch today's order book from Shoonya."""
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
