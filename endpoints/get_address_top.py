# encoding: utf-8
import time
from typing import List

from fastapi import Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.future import select
from starlette.responses import Response

from constants import ADDRESS_RANKINGS
from dbsession import async_session
from endpoints import sql_db_only
from models.TopScript import TopScript
from server import app


class TopAddress(BaseModel):
    rank: int
    address: str
    amount: int


class TopAddresses(BaseModel):
    timestamp: int
    ranking: List[TopAddress]


@app.get(
    "/addresses/top",
    response_model=List[TopAddresses],
    tags=["Kaspa addresses"],
    summary="EXPERIMENTAL - EXPECT BREAKING CHANGES: Get top Kaspa addresses (rich list)",
    description="Get top addresses, use 'before' to get historical data (must be divisible by limit).",
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_addresses_top(
    response: Response, before: int | None = Query(None), limit: int = Query(default=1, enum=[1])
):
    if not ADDRESS_RANKINGS:
        raise HTTPException(status_code=503, detail="Top addresses is disabled")
    if limit not in [1]:
        raise HTTPException(400, "'limit' must be in [1]")

    response.headers["Cache-Control"] = "public, max-age=60"
    if before is not None:
        if before % 3_600_000 != 0:
            raise HTTPException(status_code=400, detail="'before' must be aligned to a full hour")
        now_ms = int(time.time() * 1000)
        if before < now_ms - 3_600_000:
            response.headers["Cache-Control"] = "public, max-age=86400"
        elif before > now_ms + 600_000:
            return []

    async with async_session() as s:
        ts_subquery = select(TopScript.timestamp).distinct().order_by(TopScript.timestamp.desc()).limit(limit)
        if before is not None:
            ts_subquery = ts_subquery.where(TopScript.timestamp < before)
        top_scripts = (
            (
                await s.execute(
                    select(TopScript)
                    .where(TopScript.timestamp.in_(ts_subquery))
                    .order_by(TopScript.timestamp.desc(), TopScript.rank)
                )
            )
            .scalars()
            .all()
        )

    grouped: dict[int, list[TopScript]] = {}
    for ts in top_scripts:
        grouped.setdefault(ts.timestamp, []).append(ts)

    return [
        TopAddresses(
            timestamp=ts,
            ranking=[
                TopAddress(rank=t.rank, address=t.script_public_key_address, amount=t.amount) for t in grouped[ts]
            ],
        )
        for ts in sorted(grouped.keys(), reverse=True)
    ]
