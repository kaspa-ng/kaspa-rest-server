import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_logger = logging.getLogger(__name__)

Base = declarative_base()


def _make_engine(uri: str):
    return create_async_engine(
        uri,
        pool_pre_ping=True,
        pool_size=int(os.getenv("SQL_POOL_SIZE", "15")),
        max_overflow=int(os.getenv("SQL_POOL_MAX_OVERFLOW", "0")),
        pool_recycle=int(os.getenv("SQL_POOL_RECYCLE_SECONDS", "1200")),
        echo=os.getenv("DEBUG") == "true",
    )


primary_engine = _make_engine(os.getenv("SQL_URI", "postgresql+asyncpg://127.0.0.1:5432"))
async_session_factory = sessionmaker(primary_engine, expire_on_commit=False, class_=AsyncSession)


def async_session():
    return async_session_factory()


if os.getenv("SQL_URI_BLOCKS"):
    blocks_engine = _make_engine(os.getenv("SQL_URI_BLOCKS"))
    async_session_blocks_factory = sessionmaker(blocks_engine, expire_on_commit=False, class_=AsyncSession)

    def async_session_blocks():
        return async_session_blocks_factory()
else:

    def async_session_blocks():
        return async_session_factory()
