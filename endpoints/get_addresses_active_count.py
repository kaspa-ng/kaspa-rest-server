# encoding: utf-8
import calendar
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi import Path
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.future import select
from starlette.responses import Response

from constants import (
    A_DAY_MS,
    AN_HOUR_MS,
    GENESIS_START_OF_DAY_MS,
    GENESIS_START_OF_MONTH_MS,
    REGEX_DATE_OPTIONAL_DAY,
    ADDRESSES_ACTIVE_COUNT,
    USE_SCRIPT_FOR_ADDRESS,
)
from dbsession import async_session
from models.ScriptsActiveCount import ScriptsActiveCount
from models.TxAddrMapping import TxScriptCount, TxAddrCount
from server import app

_logger = logging.getLogger(__name__)
_table_exists: bool | None = None


class AddressesActiveCountResponse(BaseModel):
    timestamp: int
    dateTime: str
    count: int


@app.get(
    "/addresses/active/count/",
    response_model=AddressesActiveCountResponse,
    tags=["Kaspa addresses"],
    summary="EXPERIMENTAL - EXPECT BREAKING CHANGES: Get the total count of active addresses",
)
async def get_addresses_active_count_totals(response: Response):
    if not ADDRESSES_ACTIVE_COUNT:
        raise HTTPException(status_code=503, detail="Addresses active count is disabled")

    response.headers["Cache-Control"] = "public, max-age=600, stale-while-revalidate=300"

    async with async_session() as s:
        global _table_exists
        if _table_exists is None:
            if USE_SCRIPT_FOR_ADDRESS:
                table_name = TxScriptCount.__tablename__
            else:
                table_name = TxAddrCount.__tablename__
            check_table_exists_sql = text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_name = '{table_name}'
                    );
                """)
            result = await s.execute(check_table_exists_sql)
            _table_exists = result.scalar()

        if not _table_exists:
            raise HTTPException(status_code=503, detail="Addresses active total count is not available")

        if USE_SCRIPT_FOR_ADDRESS:
            result = await s.execute(select(func.count()).select_from(TxScriptCount))
        else:
            result = await s.execute(select(func.count()).select_from(TxAddrCount))

        count = result.scalar_one()
        if count == 0:
            raise HTTPException(status_code=404, detail="Addresses active total count is not available")

        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        return AddressesActiveCountResponse(
            timestamp=now,
            dateTime=datetime.fromtimestamp(now / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            count=count,
        )


@app.get(
    "/addresses/active/count/{day_or_month}",
    response_model=list[AddressesActiveCountResponse],
    tags=["Kaspa addresses"],
    summary="EXPERIMENTAL - EXPECT BREAKING CHANGES: Get the count of active addresses for a specific UTC day (YYYY-MM-DD) or month (YYYY-MM)",
)
async def get_addresses_active_count_for_day(
    response: Response, day_or_month: str = Path(pattern=REGEX_DATE_OPTIONAL_DAY)
):
    if not ADDRESSES_ACTIVE_COUNT:
        raise HTTPException(status_code=503, detail="Addresses active count is disabled")

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
            select(ScriptsActiveCount)
            .where(ScriptsActiveCount.timestamp >= start_ms, ScriptsActiveCount.timestamp < end_ms)
            .order_by(ScriptsActiveCount.timestamp)
        )
        rows = result.scalars().all()
        return [
            AddressesActiveCountResponse(
                timestamp=row.timestamp,
                dateTime=datetime.fromtimestamp(row.timestamp / 1000, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                count=row.count,
            )
            for row in rows
        ]
