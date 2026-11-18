from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from bot.config import get_settings

def make_engine():
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is missing in .env")
    return create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)

def make_session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)
