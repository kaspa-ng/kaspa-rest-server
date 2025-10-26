# encoding: utf-8
import calendar
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi import Path
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.future import select
from starlette.responses import Response

from constants import (
    A_DAY_MS,
    AN_HOUR_MS,
    GENESIS_START_OF_DAY_MS,
    GENESIS_START_OF_MONTH_MS,
    REGEX_DATE_OPTIONAL_DAY,
    TRANSACTION_COUNT,
)
from dbsession import async_session
from models.TransactionCount import TransactionCount
from server import app

_logger = logging.getLogger(__name__)


class TransactionCountResponse(BaseModel):
    timestamp: int
    dateTime: str
    coinbase: int
    regular: int


@app.get(
    "/transactions/count/",
    response_model=TransactionCountResponse,
    tags=["Kaspa transactions"],
    summary="EXPERIMENTAL - EXPECT BREAKING CHANGES: Get the sum of accepted transactions",
)
async def get_transaction_count_totals(response: Response):
    if not TRANSACTION_COUNT:
        raise HTTPException(status_code=503, detail="Transaction count is disabled")

    response.headers["Cache-Control"] = "public, max-age=300"

    async with async_session() as s:
        result = await s.execute(
            select(
                func.max(TransactionCount.timestamp),
                func.sum(TransactionCount.coinbase),
                func.sum(TransactionCount.regular),
            )
        )
        max_ts, coinbase_sum, regular_sum = result.one()
        if max_ts is None:
            raise HTTPException(status_code=404, detail="No transaction counts available")

        return TransactionCountResponse(
            timestamp=max_ts,
            dateTime=datetime.fromtimestamp(max_ts / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            coinbase=coinbase_sum or 0,
            regular=regular_sum or 0,
        )


@app.get(
    "/transactions/count/{day_or_month}",
    response_model=list[TransactionCountResponse],
    tags=["Kaspa transactions"],
    summary="EXPERIMENTAL - EXPECT BREAKING CHANGES: Get the number of accepted transactions for a specific UTC day (YYYY-MM-DD) or month (YYYY-MM)",
)
async def get_transaction_count_for_day(response: Response, day_or_month: str = Path(pattern=REGEX_DATE_OPTIONAL_DAY)):
    if not TRANSACTION_COUNT:
        raise HTTPException(status_code=503, detail="Transaction count is disabled")

    now = datetime.now(tz=timezone.utc)
    now_ms = now.timestamp() * 1000

    response.headers["Cache-Control"] = "public, max-age=300"

    if len(day_or_month) == 10:
        dt = datetime.strptime(day_or_month, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        start_ms = int(dt.timestamp() * 1000)
        if start_ms < GENESIS_START_OF_DAY_MS or start_ms > now_ms:
            return []
        end_ms = start_ms + A_DAY_MS
    else:
        dt = datetime.strptime(day_or_month, "%Y-%m").replace(tzinfo=timezone.utc)
        start_ms = int(dt.timestamp() * 1000)
        _, days_in_month = calendar.monthrange(dt.year, dt.month)
        end_ms = start_ms + days_in_month * A_DAY_MS
        if start_ms < GENESIS_START_OF_MONTH_MS or start_ms > now_ms:
            return []

    if end_ms < now_ms - 2 * A_DAY_MS:
        response.headers["Cache-Control"] = "public, max-age=3600"
    elif end_ms < now_ms - 2 * AN_HOUR_MS:
        response.headers["Cache-Control"] = "public, max-age=600"

    async with async_session() as s:
        result = await s.execute(
            select(TransactionCount)
            .where(TransactionCount.timestamp >= start_ms, TransactionCount.timestamp < end_ms)
            .order_by(TransactionCount.timestamp)
        )
        rows = result.scalars().all()
        return [
            TransactionCountResponse(
                timestamp=row.timestamp,
                dateTime=datetime.fromtimestamp(row.timestamp / 1000, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                coinbase=row.coinbase,
                regular=row.regular,
            )
            for row in rows
        ]
