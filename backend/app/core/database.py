from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine_kwargs = {"echo": False}
if "sqlite" not in settings.DATABASE_URL:
    engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    })

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql(
            "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS version VARCHAR DEFAULT '1'"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS live_enabled BOOLEAN DEFAULT TRUE"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS warmup_bars INTEGER DEFAULT 1"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS max_positions INTEGER DEFAULT 1"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE user_strategy_map ADD COLUMN IF NOT EXISTS engine_version VARCHAR"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE terminal_rows ADD COLUMN IF NOT EXISTS target_formula VARCHAR"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE terminal_rows ADD COLUMN IF NOT EXISTS sl_formula VARCHAR"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE terminal_columns ADD COLUMN IF NOT EXISTS book VARCHAR DEFAULT 'equity'"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE bsa_algo_rows ADD COLUMN IF NOT EXISTS custom_target FLOAT"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE bsa_algo_rows ADD COLUMN IF NOT EXISTS trade_mode VARCHAR DEFAULT 'FULL'"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE bsa_algo_rows ADD COLUMN IF NOT EXISTS entry_type VARCHAR DEFAULT 'FORMULA'"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE bsa_algo_rows ADD COLUMN IF NOT EXISTS custom_entry FLOAT"
        )
        # Ensure options contracts in bsa_algo_rows have segment = 'NSE_FNO'
        await conn.exec_driver_sql("""
            UPDATE bsa_algo_rows
            SET segment = 'NSE_FNO'
            WHERE segment IS DISTINCT FROM 'NSE_FNO'
              AND (
                symbol ILIKE '%CALL%' OR symbol ILIKE '%PUT%' OR
                symbol ILIKE '% CE%' OR symbol ILIKE '% PE%' OR
                symbol ILIKE '%-CE%' OR symbol ILIKE '%-PE%' OR
                symbol ILIKE '%OPT%' OR symbol ILIKE '%FUT%'
              )
        """)
        # Migrate target types to TGT1..TGT5
        await conn.exec_driver_sql("""
            UPDATE bsa_algo_rows
            SET target_type = 'TGT1'
            WHERE target_type IN ('T1', 'T11.8', 'T11_8') OR target_type IS NULL OR target_type = ''
        """)
        await conn.exec_driver_sql("""
            UPDATE bsa_algo_rows
            SET target_type = 'TGT2'
            WHERE target_type IN ('T2', 'T23.8', 'T23_8')
        """)
        await conn.exec_driver_sql("""
            UPDATE bsa_algo_rows
            SET target_type = 'TGT3'
            WHERE target_type IN ('T3', 'T38.2', 'T38_2')
        """)
        await conn.exec_driver_sql("""
            UPDATE bsa_algo_rows
            SET target_type = 'TGT4'
            WHERE target_type IN ('T4', 'T50')
        """)
        await conn.exec_driver_sql("""
            UPDATE bsa_algo_rows
            SET target_type = 'TGT5'
            WHERE target_type IN ('T5', 'T61.8', 'T61_8')
        """)
        # Remove legacy Fibonacci formula columns
        await conn.exec_driver_sql("""
            DELETE FROM terminal_columns
            WHERE name IN (
                'T11.8', 'T23.8', 'T38.2', 'T50', 'T61.8', 'T78.6',
                'T100', 'T1.618', 'T2.618', 'HCG', 'OCG', 'LCG', 'SSIG'
            )
        """)
        await conn.exec_driver_sql(
            "UPDATE terminal_columns SET book = 'shared' WHERE formula IS NULL AND book IS DISTINCT FROM 'shared'"
        )
        # Migrate any legacy shoonya accounts to dhan
        await conn.exec_driver_sql(
            "UPDATE broker_accounts SET broker = 'dhan' WHERE broker::text = 'shoonya'"
        )
        # Clean up any duplicate terminal columns in DB
        await conn.exec_driver_sql("""
            DELETE FROM terminal_columns
            WHERE id IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY user_id, lower(name), coalesce(book, 'shared')
                        ORDER BY created_at DESC, id
                    ) as rnum
                    FROM terminal_columns
                ) t
                WHERE t.rnum > 1
            )
        """)
        # Copy Trading Migrations
        await conn.exec_driver_sql(
            "ALTER TABLE broker_accounts ADD COLUMN IF NOT EXISTS account_role VARCHAR DEFAULT 'CHILD'"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE broker_accounts ADD COLUMN IF NOT EXISTS account_name VARCHAR"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE broker_accounts ADD COLUMN IF NOT EXISTS is_copy_enabled BOOLEAN DEFAULT TRUE"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE broker_accounts ADD COLUMN IF NOT EXISTS fixed_qty_equity INTEGER DEFAULT 10"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE broker_accounts ADD COLUMN IF NOT EXISTS fixed_lots_fno INTEGER DEFAULT 1"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE broker_accounts ADD COLUMN IF NOT EXISTS max_loss_limit FLOAT"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE broker_accounts ADD COLUMN IF NOT EXISTS force_market_order BOOLEAN DEFAULT TRUE"
        )
        # Default first active broker account to MASTER if none exists
        await conn.exec_driver_sql("""
            UPDATE broker_accounts
            SET account_role = 'MASTER', account_name = COALESCE(account_name, 'Primary Master Account')
            WHERE id = (
                SELECT id FROM broker_accounts
                WHERE is_active = TRUE
                ORDER BY created_at ASC
                LIMIT 1
            ) AND NOT EXISTS (
                SELECT 1 FROM broker_accounts WHERE account_role = 'MASTER'
            )
        """)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
