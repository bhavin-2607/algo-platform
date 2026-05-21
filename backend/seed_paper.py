#!/usr/bin/env python3
"""
Paper Trading Seed Script
=========================
Seeds both Moving Average Crossover and Opening Range Fibonacci strategies.
"""
import asyncio, sys, os, uuid
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal, init_db
from app.models.user import User
from app.models.broker import BrokerAccount, BrokerName
from app.models.strategy import Strategy, UserStrategyMap, StrategyStatus

STRATEGIES = [
    {
        "name":        "Moving Average Crossover",
        "description": "Generates BUY/SELL signals when fast MA crosses slow MA.",
        "engine_class":"moving_average_crossover",
        "default_params": {
            "symbol":"RELIANCE","exchange":"NSE","token":"2885",
            "fast":9,"slow":21,"quantity":1,"timeframe_minutes":1,
            "daily_loss_limit":2000,"max_exposure":50000,
            "max_quantity":10,"max_losses":3,"base_price":2800.0,
        },
    },
    {
        "name":        "Opening Range Fibonacci",
        "description": "Trades the 9:15 AM open using square-root entry and Fibonacci targets.",
        "engine_class":"opening_range_fibonacci",
        "default_params": {
            "symbol":"NIFTY50","exchange":"NSE","token":"26000",
            "quantity":1,"target_level":"T3","sl_pct":0.5,
            "daily_loss_limit":3000,"max_exposure":100000,
            "max_quantity":5,"max_losses":2,"base_price":24800.0,
        },
    },
]

async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).order_by(User.created_at))
        user = result.scalars().first()
        if not user:
            print("❌  No users found. Register first via the UI.")
            return
        print(f"✅  User: {user.username}")

        # Broker account
        existing_ba = await db.execute(
            select(BrokerAccount).where(
                BrokerAccount.user_id == user.id,
                BrokerAccount.broker  == BrokerName.shoonya,
                BrokerAccount.paper_trading == True,
            )
        )
        ba = existing_ba.scalar_one_or_none()
        if not ba:
            ba = BrokerAccount(
                id=uuid.uuid4(), user_id=user.id,
                broker=BrokerName.shoonya, client_id="PAPER_TEST_001",
                paper_trading=True, is_active=True,
            )
            db.add(ba)
            await db.flush()
            print(f"✅  Paper broker account created: {ba.id}")
        else:
            print(f"✅  Broker account exists: {ba.id}")

        for strat_def in STRATEGIES:
            existing = await db.execute(
                select(Strategy).where(Strategy.engine_class == strat_def["engine_class"])
            )
            strat = existing.scalar_one_or_none()
            if not strat:
                strat = Strategy(
                    id=uuid.uuid4(), name=strat_def["name"],
                    description=strat_def["description"],
                    engine_class=strat_def["engine_class"],
                    default_params=strat_def["default_params"],
                    is_available=True,
                )
                db.add(strat)
                await db.flush()
                print(f"✅  Created strategy: {strat.name}")
            else:
                print(f"✅  Strategy exists: {strat.name}")

            existing_usm = await db.execute(
                select(UserStrategyMap).where(
                    UserStrategyMap.user_id     == user.id,
                    UserStrategyMap.strategy_id == strat.id,
                )
            )
            if not existing_usm.scalar_one_or_none():
                usm = UserStrategyMap(
                    id=uuid.uuid4(), user_id=user.id,
                    strategy_id=strat.id,
                    broker_account_id=ba.id,
                    params=strat_def["default_params"],
                    status=StrategyStatus.stopped,
                    paper_trading=True,
                )
                db.add(usm)
                print(f"✅  Assigned: {strat.name} → {user.username}")

        await db.commit()
        print("\n✅  Seed complete — go to /strategies to start trading")

if __name__ == "__main__":
    asyncio.run(seed())
