from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
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
        # Migrate legacy BSA target types to Fibonacci T1..T3
        await conn.exec_driver_sql("""
            UPDATE bsa_algo_rows
            SET target_type = 'T1'
            WHERE target_type = 'TGT1' OR target_type IS NULL OR target_type = ''
        """)
        await conn.exec_driver_sql("""
            UPDATE bsa_algo_rows
            SET target_type = 'T2'
            WHERE target_type = 'TGT2'
        """)
        await conn.exec_driver_sql("""
            UPDATE bsa_algo_rows
            SET target_type = 'T3'
            WHERE target_type = 'TGT3'
        """)
        # Remove legacy BSA formula columns
        await conn.exec_driver_sql("""
            DELETE FROM terminal_columns
            WHERE name IN (
                'INTRASIGNAL', 'OHLSIG', 'S-SIGNAL', 'DIFF',
                'BT1', 'BT2', 'BT3', 'ST1', 'ST2', 'ST3',
                'TGT1', 'TGT2', 'TGT3', 'P.CLOSE', 'P.HIGH', 'P.LOW'
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


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
