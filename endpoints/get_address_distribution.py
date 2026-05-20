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
from models.DistributionTier import DistributionTier as DbDistributionTier
from server import app


class DistributionTier(BaseModel):
    tier: int
    count: int
    amount: int


class DistributionTiers(BaseModel):
    timestamp: int
    tiers: List[DistributionTier]


@app.get(
    "/addresses/distribution",
    response_model=List[DistributionTiers],
    tags=["Kaspa addresses"],
    summary="EXPERIMENTAL - EXPECT BREAKING CHANGES: Get Kaspa address distribution by balance tier",
    description="Get address distribution tiers, use 'before' to get historical data (must be divisible by limit).\n\n"
    "Addresses are grouped by their balance (KAS) in powers of ten. Tier 0:[0.0001..1), 1:[1..10), ..., 10:[1b..10b).",
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_distribution_tiers(
    response: Response, before: int | None = Query(None), limit: int = Query(default=1, enum=[1, 24])
):
    if not ADDRESS_RANKINGS:
        raise HTTPException(status_code=503, detail="Distribution tiers is disabled")
    if limit not in [1, 24]:
        raise HTTPException(400, "'limit' must be in [1, 24]")

    response.headers["Cache-Control"] = "public, max-age=180"
    if before is not None:
        if limit == 24 and before % 86_400_000 != 0:
            raise HTTPException(status_code=400, detail="'before' must be aligned to start of day")
        if before % 3_600_000 != 0:
            raise HTTPException(status_code=400, detail="'before' must be aligned to start of hour")
        now_ms = int(time.time() * 1000)
        if before < now_ms - 3_600_000:
            response.headers["Cache-Control"] = "public, max-age=86400"
        elif before > now_ms + 600_000:
            return []

    async with async_session() as s:
        ts_subquery = (
            select(DbDistributionTier.timestamp).distinct().order_by(DbDistributionTier.timestamp.desc()).limit(limit)
        )
        if before is not None:
            ts_subquery = ts_subquery.where(DbDistributionTier.timestamp < before)
        distribution_tiers = (
            (
                await s.execute(
                    select(DbDistributionTier)
                    .where(DbDistributionTier.timestamp.in_(ts_subquery))
                    .order_by(DbDistributionTier.timestamp.desc(), DbDistributionTier.tier)
                )
            )
            .scalars()
            .all()
        )

    grouped: dict[int, list[DbDistributionTier]] = {}
    for dt in distribution_tiers:
        grouped.setdefault(dt.timestamp, []).append(dt)

    return [
        DistributionTiers(
            timestamp=ts,
            tiers=[DistributionTier(tier=dt.tier, count=dt.count, amount=dt.amount) for dt in grouped[ts]],
        )
        for ts in sorted(grouped.keys(), reverse=True)
    ]
