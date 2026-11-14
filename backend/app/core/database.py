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
            "UPDATE terminal_columns SET book = 'shared' WHERE formula IS NULL AND book IS DISTINCT FROM 'shared'"
        )


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
