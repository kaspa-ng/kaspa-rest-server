# encoding: utf-8
import calendar
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from fastapi.params import Query
from pydantic import BaseModel
from sqlalchemy import select
from starlette.responses import Response

from fastapi import Path
from constants import (
    HASHRATE_HISTORY,
    A_DAY_MS,
    GENESIS_START_OF_DAY_MS,
    AN_HOUR_MS,
    REGEX_DATE_OPTIONAL_DAY,
    GENESIS_START_OF_MONTH_MS,
    CRESCENDO_BS,
)
from dbsession import async_session
from helper.difficulty_calculation import bits_to_difficulty
from models.HashrateHistory import HashrateHistory
from server import app

_logger = logging.getLogger(__name__)


class HashrateHistoryResponse(BaseModel):
    daaScore: int
    blueScore: int
    timestamp: int
    date_time: str
    bits: int | None
    difficulty: int
    hashrate_kh: int


_sample_interval_minutes = 15


@app.get(
    "/info/hashrate/history/{day_or_month}",
    response_model=list[HashrateHistoryResponse],
    tags=["Kaspa network info"],
)
async def get_hashrate_history_for_day_or_month(
    response: Response,
    day_or_month: str = Path(pattern=REGEX_DATE_OPTIONAL_DAY),
    resolution: Optional[str] = Query(default=None, enum=["15m", "1h"]),
):
    """
    Get hashrate history for a specific UTC day (YYYY-MM-DD) or month (YYYY-MM)
    """
    if not HASHRATE_HISTORY:
        raise HTTPException(status_code=503, detail="Hashrate history is disabled")

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

    resolution_map = {
        None: int(15 / _sample_interval_minutes),
        "15m": int(15 / _sample_interval_minutes),
        "1h": int(60 / _sample_interval_minutes),
    }
    sample_interval = resolution_map.get(resolution)
    if not sample_interval:
        raise HTTPException(status_code=400, detail=f"Invalid resolution, allowed: {list(resolution_map.keys())}")

    async with async_session() as s:
        result = await s.execute(
            select(HashrateHistory)
            .where(HashrateHistory.timestamp >= start_ms)
            .where(HashrateHistory.timestamp < end_ms)
            .order_by(HashrateHistory.daa_score.desc())
        )
        samples = result.scalars().all()
        return filter_samples(samples, sample_interval)


@app.get("/info/hashrate/history", response_model=list[HashrateHistoryResponse], tags=["Kaspa network info"])
async def get_hashrate_history(
    response: Response, resolution: Optional[str] = Query(default=None, enum=["15m", "1h", "3h", "1d", "7d"])
):
    """
    Get historical hashrate samples with optional resolution (default = 1h)
    """
    if not HASHRATE_HISTORY:
        raise HTTPException(status_code=503, detail="Hashrate history is disabled")

    response.headers["Cache-Control"] = "public, max-age=3600"

    resolution_map = {
        None: int(60 / _sample_interval_minutes),
        "15m": int(15 / _sample_interval_minutes),
        "1h": int(60 / _sample_interval_minutes),
        "3h": int(3 * 60 / _sample_interval_minutes),
        "1d": int(24 * 60 / _sample_interval_minutes),
        "7d": int(7 * 24 * 60 / _sample_interval_minutes),
    }
    sample_interval = resolution_map.get(resolution)
    if not sample_interval:
        raise HTTPException(status_code=400, detail=f"Invalid resolution, allowed: {list(resolution_map.keys())}")

    async with async_session() as s:
        result = await s.execute(select(HashrateHistory).order_by(HashrateHistory.daa_score.desc()))
        samples = result.scalars().all()
        return filter_samples(samples, sample_interval)


def filter_samples(samples: list[HashrateHistory], sample_interval: int) -> list[HashrateHistoryResponse]:
    samples_filtered = []
    for i in range(0, len(samples), sample_interval):
        chunk = samples[i : i + sample_interval]
        first = chunk[-1]
        last = chunk[0]
        # If sampling and crossing the crescendo activation, we must create one sample before and one after
        # Otherwise there will be artifacts produced in the graph due to the sudden reduction in difficulty
        if first.blue_score < CRESCENDO_BS <= last.blue_score:
            difficulty = int(bits_to_difficulty(first.bits))
            hashrate_kh = difficulty * 2 // 1_000
            samples_filtered.append(hashrate_history(first, None, difficulty, hashrate_kh))
            difficulty = int(bits_to_difficulty(last.bits))
            hashrate_kh = difficulty * 2 * 10 // 1_000
            samples_filtered.append(hashrate_history(last, None, difficulty, hashrate_kh))
        else:
            bits = last.bits if sample_interval == 1 else None
            difficulty = int(sum(bits_to_difficulty(s.bits) for s in chunk) / len(chunk))
            hashrate_kh = difficulty * 2 * (1 if last.blue_score < CRESCENDO_BS else 10) // 1_000
            samples_filtered.append(hashrate_history(last, bits, difficulty, hashrate_kh))
    return samples_filtered


def hashrate_history(sample, bits, difficulty, hashrate_kh):
    return {
        "daaScore": sample.daa_score,
        "blueScore": sample.blue_score,
        "timestamp": sample.timestamp,
        "date_time": datetime.fromtimestamp(sample.timestamp / 1000, tz=timezone.utc).isoformat(
            timespec="milliseconds"
        ),
        "bits": bits,
        "difficulty": difficulty,
        "hashrate_kh": hashrate_kh,
    }
