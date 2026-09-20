from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from .base import Base
from backend.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


from sqlalchemy import text


async def create_tables() -> None:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("ALTER TABLE monthly_channel_metrics ADD COLUMN IF NOT EXISTS reels_count INT DEFAULT 0;"))
            await conn.execute(text("ALTER TABLE monthly_channel_metrics ADD COLUMN IF NOT EXISTS static_post_count INT DEFAULT 0;"))
            await conn.execute(text("ALTER TABLE micro_unit_channels ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'INSTAGRAM';"))
            await conn.execute(text("ALTER TABLE micro_unit_channels ADD COLUMN IF NOT EXISTS channel_title TEXT;"))
            await conn.execute(text("ALTER TABLE micro_unit_channels ALTER COLUMN instagram_id DROP NOT NULL;"))
        print("✓ Database tables created or verified")
    except Exception as e:
        print(f"⚠️  Error creating tables: {type(e).__name__}: {e}")
        # Continue anyway - tables might already exist
        pass
