import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.broker import BrokerAccount, BrokerName
from app.models.copy_trade_log import CopyTradeLog
from app.schemas.copy_trading import (
    DhanAccountCreate,
    DhanAccountUpdate,
    DhanAccountResponse,
    CopyTradeLogResponse,
    CopyTradingSummaryResponse,
)
from app.core.security import encrypt_broker_token, decrypt_broker_token
from app.broker.factory import get_broker_adapter
from app.broker.dhan import DhanAdapter, get_public_ipv4
from app.services.dhan_fanout_engine import fanout_engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/accounts", response_model=CopyTradingSummaryResponse)
async def list_copy_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List Master Dhan account and all Follower/Child Dhan accounts
    with live status, available margin, and copy trading settings.
    """
    result = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.user_id == current_user.id,
            BrokerAccount.broker == BrokerName.dhan,
        ).order_by(BrokerAccount.created_at.asc())
    )
    accounts = result.scalars().all()

    master_resp: Optional[DhanAccountResponse] = None
    children_resp: List[DhanAccountResponse] = []

    for acc in accounts:
        # Check fund limits / margin if live
        margin = 0.0
        token_valid = True
        if not acc.paper_trading and acc.is_active:
            try:
                adapter = get_broker_adapter(acc)
                if isinstance(adapter, DhanAdapter):
                    sdk = adapter._get_sdk()
                    funds = sdk.get_fund_limits()
                    if funds and isinstance(funds, dict) and funds.get("status") == "success":
                        data = funds.get("data") or {}
                        margin = float(data.get("availMargin") or data.get("availableBalance") or 0.0)
                    else:
                        token_valid = False
            except Exception as e:
                logger.debug(f"Could not fetch fund limits for {acc.client_id}: {e}")
                token_valid = False

        acc_dict = {
            "id": acc.id,
            "user_id": acc.user_id,
            "broker": acc.broker.value,
            "client_id": acc.client_id,
            "account_role": acc.account_role or "CHILD",
            "account_name": acc.account_name or (f"Master ({acc.client_id})" if acc.account_role == "MASTER" else f"Child ({acc.client_id})"),
            "is_active": acc.is_active,
            "is_copy_enabled": acc.is_copy_enabled if acc.is_copy_enabled is not None else True,
            "paper_trading": acc.paper_trading,
            "fixed_qty_equity": acc.fixed_qty_equity or 10,
            "fixed_lots_fno": acc.fixed_lots_fno or 1,
            "max_loss_limit": acc.max_loss_limit,
            "force_market_order": acc.force_market_order if acc.force_market_order is not None else True,
            "available_margin": margin,
            "live_pnl": 0.0,
            "token_valid": token_valid,
            "created_at": acc.created_at,
        }
        resp_model = DhanAccountResponse.model_validate(acc_dict)

        if acc.account_role == "MASTER":
            if master_resp is None:
                master_resp = resp_model
            else:
                children_resp.append(resp_model)
        else:
            children_resp.append(resp_model)

    # If no master is designated yet, designate the first active account as master
    if master_resp is None and children_resp:
        master_resp = children_resp.pop(0)
        master_resp.account_role = "MASTER"

    active_copy_count = sum(1 for c in children_resp if c.is_copy_enabled and c.is_active)

    return CopyTradingSummaryResponse(
        master_account=master_resp,
        child_accounts=children_resp,
        total_child_count=len(children_resp),
        active_copy_count=active_copy_count,
        is_copy_system_active=active_copy_count > 0,
    )


@router.post("/accounts", response_model=DhanAccountResponse, status_code=201)
async def add_dhan_account(
    payload: DhanAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Link a new Dhan account (Master or Child) with encrypted access token and copy settings.
    """
    clean_client_id = payload.client_id.strip()
    clean_token = payload.access_token.strip()

    if not clean_client_id or not clean_token:
        raise HTTPException(status_code=400, detail="Client ID and Access Token are required")

    # Check duplicate
    existing = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.user_id == current_user.id,
            BrokerAccount.broker == BrokerName.dhan,
            BrokerAccount.client_id == clean_client_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="This Dhan account is already linked")

    # If live, test connection immediately
    is_active = True
    margin = 0.0
    if not payload.paper_trading:
        adapter = DhanAdapter(client_id=clean_client_id, access_token=clean_token)
        is_connected = await adapter.connect()
        if not is_connected:
            raise HTTPException(
                status_code=400,
                detail="Could not verify Dhan credentials. Check Client ID, Access Token, or Static IP whitelisting."
            )
        try:
            sdk = adapter._get_sdk()
            funds = sdk.get_fund_limits()
            if funds and isinstance(funds, dict) and funds.get("status") == "success":
                data = funds.get("data") or {}
                margin = float(data.get("availMargin") or data.get("availableBalance") or 0.0)
        except Exception:
            pass

    # If setting as MASTER, demote any existing MASTER to CHILD
    role = (payload.account_role or "CHILD").upper()
    if role == "MASTER":
        await db.execute(
            select(BrokerAccount).where(
                BrokerAccount.user_id == current_user.id,
                BrokerAccount.account_role == "MASTER",
            )
        )
        # Update existing master to CHILD
        from sqlalchemy import update
        await db.execute(
            update(BrokerAccount)
            .where(BrokerAccount.user_id == current_user.id, BrokerAccount.account_role == "MASTER")
            .values(account_role="CHILD")
        )

    new_account = BrokerAccount(
        user_id=current_user.id,
        broker=BrokerName.dhan,
        client_id=clean_client_id,
        encrypted_access_token=encrypt_broker_token(clean_token),
        is_active=is_active,
        paper_trading=payload.paper_trading or False,
        account_role=role,
        account_name=payload.account_name or f"Dhan {clean_client_id}",
        is_copy_enabled=payload.is_copy_enabled if payload.is_copy_enabled is not None else True,
        fixed_qty_equity=max(1, payload.fixed_qty_equity or 10),
        fixed_lots_fno=max(1, payload.fixed_lots_fno or 1),
        max_loss_limit=payload.max_loss_limit,
        force_market_order=payload.force_market_order if payload.force_market_order is not None else True,
    )

    db.add(new_account)
    await db.commit()
    await db.refresh(new_account)

    acc_dict = {
        "id": new_account.id,
        "user_id": new_account.user_id,
        "broker": new_account.broker.value,
        "client_id": new_account.client_id,
        "account_role": new_account.account_role,
        "account_name": new_account.account_name,
        "is_active": new_account.is_active,
        "is_copy_enabled": new_account.is_copy_enabled,
        "paper_trading": new_account.paper_trading,
        "fixed_qty_equity": new_account.fixed_qty_equity,
        "fixed_lots_fno": new_account.fixed_lots_fno,
        "max_loss_limit": new_account.max_loss_limit,
        "force_market_order": new_account.force_market_order,
        "available_margin": margin,
        "live_pnl": 0.0,
        "token_valid": True,
        "created_at": new_account.created_at,
    }
    return DhanAccountResponse.model_validate(acc_dict)


@router.patch("/accounts/{account_id}", response_model=DhanAccountResponse)
async def update_dhan_account(
    account_id: UUID,
    payload: DhanAccountUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update configuration for a Dhan account (e.g. toggle copy trading, change fixed quantities).
    """
    account = await db.get(BrokerAccount, account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Account not found")

    if payload.account_name is not None:
        account.account_name = payload.account_name

    if payload.account_role is not None:
        new_role = payload.account_role.upper()
        if new_role == "MASTER" and account.account_role != "MASTER":
            from sqlalchemy import update
            await db.execute(
                update(BrokerAccount)
                .where(BrokerAccount.user_id == current_user.id, BrokerAccount.account_role == "MASTER")
                .values(account_role="CHILD")
            )
        account.account_role = new_role

    if payload.is_copy_enabled is not None:
        account.is_copy_enabled = payload.is_copy_enabled

    if payload.paper_trading is not None:
        account.paper_trading = payload.paper_trading

    if payload.fixed_qty_equity is not None:
        account.fixed_qty_equity = max(1, payload.fixed_qty_equity)

    if payload.fixed_lots_fno is not None:
        account.fixed_lots_fno = max(1, payload.fixed_lots_fno)

    if payload.max_loss_limit is not None:
        account.max_loss_limit = payload.max_loss_limit

    if payload.force_market_order is not None:
        account.force_market_order = payload.force_market_order

    if payload.access_token:
        clean_token = payload.access_token.strip()
        account.encrypted_access_token = encrypt_broker_token(clean_token)
        # Test connection
        if not account.paper_trading:
            adapter = DhanAdapter(client_id=account.client_id, access_token=clean_token)
            account.is_active = await adapter.connect()

    await db.commit()
    await db.refresh(account)

    acc_dict = {
        "id": account.id,
        "user_id": account.user_id,
        "broker": account.broker.value,
        "client_id": account.client_id,
        "account_role": account.account_role or "CHILD",
        "account_name": account.account_name,
        "is_active": account.is_active,
        "is_copy_enabled": account.is_copy_enabled,
        "paper_trading": account.paper_trading,
        "fixed_qty_equity": account.fixed_qty_equity or 10,
        "fixed_lots_fno": account.fixed_lots_fno or 1,
        "max_loss_limit": account.max_loss_limit,
        "force_market_order": account.force_market_order,
        "available_margin": 0.0,
        "live_pnl": 0.0,
        "token_valid": True,
        "created_at": account.created_at,
    }
    return DhanAccountResponse.model_validate(acc_dict)


@router.delete("/accounts/{account_id}", status_code=204)
async def delete_dhan_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect and remove a Dhan account."""
    account = await db.get(BrokerAccount, account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Account not found")

    await db.delete(account)
    await db.commit()


@router.post("/test-connection/{account_id}")
async def test_account_connection(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test Dhan connection, fetch margin limits, and return current outbound public IPv4."""
    account = await db.get(BrokerAccount, account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.paper_trading:
        return {
            "status": "success",
            "message": "Paper trading account active (simulation mode)",
            "available_margin": 1000000.0,
            "ip": get_public_ipv4(),
        }

    try:
        adapter = get_broker_adapter(account)
        if not isinstance(adapter, DhanAdapter):
            raise HTTPException(status_code=400, detail="Not a Dhan adapter")

        is_connected = await adapter.connect()
        if not is_connected:
            return {
                "status": "failed",
                "message": "Connection failed. Check Access Token or Static IP whitelisting.",
                "ip": get_public_ipv4(),
            }

        sdk = adapter._get_sdk()
        funds = sdk.get_fund_limits()
        margin = 0.0
        if funds and isinstance(funds, dict) and funds.get("status") == "success":
            data = funds.get("data") or {}
            margin = float(data.get("availMargin") or data.get("availableBalance") or 0.0)

        return {
            "status": "success",
            "message": "Connected and verified with DhanHQ API",
            "client_id": account.client_id,
            "available_margin": margin,
            "ip": get_public_ipv4(),
        }
    except Exception as e:
        logger.error(f"Test connection error: {e}")
        return {
            "status": "failed",
            "message": str(e),
            "ip": get_public_ipv4(),
        }


@router.get("/logs", response_model=List[CopyTradeLogResponse])
async def list_copy_trade_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch paginated audit logs of all copied trades across accounts."""
    result = await db.execute(
        select(CopyTradeLog)
        .where(CopyTradeLog.user_id == current_user.id)
        .order_by(desc(CopyTradeLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/emergency-square-off")
async def emergency_square_off(
    current_user: User = Depends(get_current_user),
):
    """
    EMERGENCY KILL SWITCH: Cancel all pending orders and market-out open positions
    across Master and all Child accounts simultaneously.
    """
    result = await fanout_engine.emergency_square_off_all_accounts(user_id=current_user.id)
    return result
