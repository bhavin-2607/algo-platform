import logging
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sa_delete, update as sa_update
from app.models.broker import BrokerAccount

logger = logging.getLogger(__name__)


async def purge_broker_account(db: AsyncSession, account: BrokerAccount) -> None:
    """
    Safely decouple and delete a BrokerAccount, cleaning up or nullifying
    all foreign key references across trades, copy trade logs, terminal rows,
    managed positions, strategy maps, and signals to avoid IntegrityError.
    """
    account_id = account.id
    logger.info(f"Purging broker account {account_id} (Client ID: {account.client_id}, Broker: {account.broker})")

    # 1. Delete copy trade logs (hard FK constraint, non-nullable)
    try:
        from app.models.copy_trade_log import CopyTradeLog
        await db.execute(
            sa_delete(CopyTradeLog).where(CopyTradeLog.broker_account_id == account_id)
        )
    except Exception as e:
        logger.warning(f"Error purging CopyTradeLog for {account_id}: {e}")

    # 2. Delete user strategy maps
    try:
        from app.models.strategy import UserStrategyMap
        await db.execute(
            sa_delete(UserStrategyMap).where(UserStrategyMap.broker_account_id == account_id)
        )
    except Exception as e:
        logger.warning(f"Error purging UserStrategyMap for {account_id}: {e}")

    # 3. Delete copy relationships
    try:
        from app.models.signal import CopyRelationship
        await db.execute(
            sa_delete(CopyRelationship).where(CopyRelationship.broker_account_id == account_id)
        )
    except Exception as e:
        logger.warning(f"Error purging CopyRelationship for {account_id}: {e}")

    # 4. Nullify signal executions
    try:
        from app.models.signal import SignalExecution
        await db.execute(
            sa_update(SignalExecution)
            .where(SignalExecution.broker_account_id == account_id)
            .values(broker_account_id=None)
        )
    except Exception as e:
        logger.warning(f"Error unlinking SignalExecution for {account_id}: {e}")

    # 5. Delete managed positions and nullify formula strategies
    try:
        from app.models.formula import ManagedPosition, FormulaStrategy
        await db.execute(
            sa_delete(ManagedPosition).where(ManagedPosition.broker_account_id == account_id)
        )
        await db.execute(
            sa_update(FormulaStrategy)
            .where(FormulaStrategy.broker_account_id == account_id)
            .values(broker_account_id=None)
        )
    except Exception as e:
        logger.warning(f"Error purging formula positions/strategies for {account_id}: {e}")

    # 6. Nullify terminal rows
    try:
        from app.models.terminal import TerminalRow
        await db.execute(
            sa_update(TerminalRow)
            .where(TerminalRow.broker_account_id == account_id)
            .values(broker_account_id=None)
        )
    except Exception as e:
        logger.warning(f"Error unlinking TerminalRow for {account_id}: {e}")

    # 7. Nullify trades (preserves trade record history while safely detaching account)
    try:
        from app.models.trade import Trade
        await db.execute(
            sa_update(Trade)
            .where(Trade.broker_account_id == account_id)
            .values(broker_account_id=None)
        )
    except Exception as e:
        logger.warning(f"Error unlinking Trade for {account_id}: {e}")

    # 8. Delete the broker account itself
    await db.delete(account)
    await db.commit()
    logger.info(f"Successfully purged broker account {account_id}")
