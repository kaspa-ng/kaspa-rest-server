import logging
import os

import psycopg
from psycopg.types.composite import CompositeInfo, register_composite
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from models.TransactionTypes import TransactionInput, TransactionOutput

_logger = logging.getLogger(__name__)

Base = declarative_base()


def psycopg_dsn_from_sqlalchemy_url(sqlalchemy_url: str) -> str:
    url = make_url(sqlalchemy_url)
    return f"dbname={url.database} user={url.username} password={url.password} host={url.host} port={url.port}"


def setup_composites(sqlalchemy_url: str):
    dsn = psycopg_dsn_from_sqlalchemy_url(sqlalchemy_url)
    with psycopg.connect(dsn) as conn:
        info_in = CompositeInfo.fetch(conn, "transactions_inputs")
        register_composite(info_in, None, factory=TransactionInput)
        info_out = CompositeInfo.fetch(conn, "transactions_outputs")
        register_composite(info_out, None, factory=TransactionOutput)


setup_composites(os.getenv("SQL_URI", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"))


def _make_engine(uri: str):
    return create_async_engine(
        uri,
        pool_pre_ping=True,
        pool_size=int(os.getenv("SQL_POOL_SIZE", "15")),
        max_overflow=int(os.getenv("SQL_POOL_MAX_OVERFLOW", "0")),
        pool_recycle=int(os.getenv("SQL_POOL_RECYCLE_SECONDS", "1200")),
        echo=os.getenv("DEBUG") == "true",
    )


primary_engine = _make_engine(os.getenv("SQL_URI", "postgresql+psycopg://127.0.0.1:5432"))
async_session_factory = sessionmaker(primary_engine, expire_on_commit=False, class_=AsyncSession)


def async_session():
    return async_session_factory()
