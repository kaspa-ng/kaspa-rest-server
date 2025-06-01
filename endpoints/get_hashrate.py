# encoding: utf-8
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import HTTPException
from fastapi.params import Query
from fastapi_utils.tasks import repeat_every
from pydantic import BaseModel
from sqlalchemy import select, text, func
from starlette.responses import Response

from constants import BPS, HASHRATE_HISTORY
from dbsession import async_session_blocks
from endpoints import sql_db_only
from endpoints.get_virtual_chain_blue_score import get_virtual_selected_parent_blue_score
from helper import KeyValueStore
from helper.difficulty_calculation import bits_to_difficulty
from models.Block import Block
from models.HashrateHistory import HashrateHistory
from server import app, kaspad_client

_logger = logging.getLogger(__name__)


class BlockHeader(BaseModel):
    hash: str = "e6641454e16cff4f232b899564eeaa6e480b66069d87bee6a2b2476e63fcd887"
    timestamp: str = "1656450648874"
    difficulty: int = 1212312312
    daaScore: str = "19984482"
    blueScore: str = "18483232"


class HashrateResponse(BaseModel):
    hashrate: float = 12000132


class MaxHashrateResponse(BaseModel):
    hashrate: float = 12000132
    blockheader: BlockHeader


class HashrateHistoryResponse(BaseModel):
    daaScore: int
    blueScore: int
    timestamp: int
    date_time: str
    bits: int
    difficulty: int
    hashrate_in_kh: int


@app.get("/info/hashrate", response_model=HashrateResponse | str, tags=["Kaspa network info"])
async def get_hashrate(stringOnly: bool = False):
    """
    Returns the current hashrate for Kaspa network in TH/s.
    """

    resp = await kaspad_client.request("getBlockDagInfoRequest")
    hashrate = resp["getBlockDagInfoResponse"]["difficulty"] * 2 * BPS
    hashrate_in_th = hashrate / 1_000_000_000_000

    if not stringOnly:
        return {"hashrate": hashrate_in_th}

    else:
        return f"{hashrate_in_th:.01f}"


@app.get("/info/hashrate/max", response_model=MaxHashrateResponse, tags=["Kaspa network info"])
@sql_db_only
async def get_max_hashrate():
    """
    Returns the current hashrate for Kaspa network in TH/s.
    """
    maxhash_last_value = json.loads((await KeyValueStore.get("maxhash_last_value")) or "{}")
    maxhash_last_bluescore = int((await KeyValueStore.get("maxhash_last_bluescore")) or 0)

    async with async_session_blocks() as s:
        block = (
            await s.execute(
                select(Block)
                .filter(Block.blue_score > maxhash_last_bluescore)
                .order_by(Block.bits.asc())  # bits and difficulty is inversely proportional
                .limit(1)
            )
        ).scalar()

    hashrate_old = maxhash_last_value.get("blockheader", {}).get("difficulty", 0) * 2 * BPS
    logging.debug(f"hashrate_old: {int(hashrate_old)}")
    if block:
        block_difficulty = bits_to_difficulty(block.bits)
        hashrate_new = block_difficulty * 2 * BPS
        logging.debug(f"hashrate_new (db): {int(hashrate_new)}")
        await KeyValueStore.set("maxhash_last_bluescore", str(block.blue_score))
        if hashrate_new > hashrate_old:
            response = {
                "hashrate": hashrate_new / 1_000_000_000_000,
                "blockheader": {
                    "hash": block.hash,
                    "timestamp": datetime.fromtimestamp(block.timestamp / 1000).isoformat(),
                    "difficulty": block_difficulty,
                    "daaScore": block.daa_score,
                    "blueScore": block.blue_score,
                },
            }
            await KeyValueStore.set("maxhash_last_value", json.dumps(response))
            return response
    else:
        resp = await kaspad_client.request("getBlockDagInfoRequest")
        block_hash = resp["getBlockDagInfoResponse"]["virtualParentHashes"][0]
        resp = await kaspad_client.request("getBlockRequest", params={"hash": block_hash, "includeTransactions": False})
        block = resp.get("getBlockResponse", {}).get("block", {})
        block_difficulty = int(block.get("verboseData", {}).get("difficulty", 0))
        hashrate_new = block_difficulty * 2 * BPS
        logging.debug(f"hashrate_new (kaspad): {int(hashrate_new)}")
        if hashrate_new > hashrate_old:
            response = {
                "hashrate": hashrate_new / 1_000_000_000_000,
                "blockheader": {
                    "hash": block.get("verboseData", {}).get("hash"),
                    "timestamp": datetime.fromtimestamp(
                        int(block.get("header", {}).get("timestamp", 0)) / 1000
                    ).isoformat(),
                    "difficulty": block_difficulty,
                    "daaScore": int(block.get("header", {}).get("daaScore", 0)),
                    "blueScore": int(block.get("header", {}).get("blueScore", 0)),
                },
            }
            await KeyValueStore.set("maxhash_last_value", json.dumps(response))
            return response

    return maxhash_last_value


_hashrate_table_exists = False
_hashrate_history_updated = False


@app.get("/info/hashrate/history", response_model=list[HashrateHistoryResponse], tags=["Kaspa network info"])
async def get_hashrate_history(response: Response, limit: Optional[Literal[10]] = Query(default=None)):
    """
    Returns historical hashrate in KH/s with a resolution of ~3 hours between samples.
    Use no limit for initial fetch (updated daily), afterward use limit (updated hourly).
    """
    if not _hashrate_table_exists or not _hashrate_history_updated:
        raise HTTPException(status_code=503, detail="Hashrate history is not available")
    if limit:
        response.headers["Cache-Control"] = "public, max-age=3600"
    else:
        response.headers["Cache-Control"] = "public, max-age=86400"

    async with async_session_blocks() as s:
        stmt = select(HashrateHistory).order_by(HashrateHistory.blue_score.desc())
        if limit:
            stmt = stmt.limit(limit)
        result = await s.execute(stmt)
        return [
            {
                "daaScore": sample.daa_score,
                "blueScore": sample.blue_score,
                "timestamp": sample.timestamp,
                "date_time": datetime.fromtimestamp(sample.timestamp / 1000, tz=timezone.utc).isoformat(
                    timespec="milliseconds"
                ),
                "bits": sample.bits,
                "difficulty": (difficulty := bits_to_difficulty(sample.bits)),
                "hashrate_in_kh": (difficulty * 2 * (1 if sample.blue_score < 108554145 else 10)) / 1_000,
            }
            for sample in sorted(result.scalars().all(), key=lambda sample: sample.daa_score, reverse=True)
        ]


if HASHRATE_HISTORY:

    @app.on_event("startup")
    async def create_hashrate_history_table_scheduled():
        await create_hashrate_history_table()

    @app.on_event("startup")
    @repeat_every(seconds=1800)
    async def update_hashrate_history_scheduled():
        await update_hashrate_history()


async def create_hashrate_history_table():
    global _hashrate_table_exists

    async with async_session_blocks() as s:
        await acquire_hashrate_history_lock(s)
        try:
            check_table_exists_sql = text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = '{HashrateHistory.__tablename__}'
                );
            """)
            result = await s.execute(check_table_exists_sql)
            _hashrate_table_exists = result.scalar()

            if _hashrate_table_exists:
                _logger.info("Hashrate history: Table already exists")
                return

            _logger.warn("Hashrate history table does not exist, attempting to create it")
            create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS {HashrateHistory.__tablename__} (
                    blue_score BIGINT PRIMARY KEY,
                    daa_score BIGINT,
                    timestamp BIGINT,
                    bits BIGINT
                );
            """
            await s.execute(text(create_table_sql))
            await s.commit()
            _hashrate_table_exists = True
        except Exception as e:
            _logger.exception(e)
            _logger.error(f"Hashrate history: Failed to create table, create it manually: \n{create_table_sql}")
        finally:
            await release_hashrate_history_lock(s)


async def update_hashrate_history():
    global _hashrate_history_updated
    sample_interval_hours = 3
    batch_size = 1000

    if not _hashrate_table_exists:
        _logger.warn(f"Hashrate history: Skipping sampling as table '{HashrateHistory.__tablename__}' doesn't exist")
        return

    _logger.info("Hashrate history: Sampling hashrate history")
    sample_count = 0
    batch = []
    async with async_session_blocks() as s:
        await acquire_hashrate_history_lock(s)
        try:
            result = await s.execute(select(func.max(HashrateHistory.blue_score)))
            max_blue_score = result.scalar_one_or_none() or 0
            bps = 1 if max_blue_score < 108554145 else 10  # Crescendo
            next_blue_score = 0
            if max_blue_score > 0:
                next_blue_score = max_blue_score + (bps * 3600 * sample_interval_hours)

            current_blue_score = await get_virtual_selected_parent_blue_score()
            while int(current_blue_score["blueScore"]) > next_blue_score:
                result = await s.execute(
                    select(Block).where(Block.blue_score > next_blue_score).order_by(Block.blue_score.asc()).limit(1)
                )
                block = result.scalar_one_or_none()
                if not block:
                    break
                if block.blue_score and block.daa_score and block.timestamp and block.bits:
                    batch.append(
                        HashrateHistory(
                            blue_score=block.blue_score,
                            daa_score=block.daa_score,
                            timestamp=block.timestamp,
                            bits=block.bits,
                        )
                    )
                    if len(batch) >= batch_size:
                        s.add_all(batch)
                        await s.commit()
                        batch.clear()
                    sample_count += 1
                    t = datetime.fromtimestamp(block.timestamp / 1000, tz=timezone.utc).isoformat(timespec="seconds")
                    _logger.info(f"Sampled hashrate: daa={block.daa_score}, timestamp={t}, bits={block.bits}")
                if block.blue_score < 1236000:  # blue_score was reset 2021-11-22, sample more often before checkpoint
                    next_blue_score = block.blue_score + 3600
                else:
                    bps = 1 if block.blue_score < 108554145 else 10
                    next_blue_score = block.blue_score + (bps * 3600 * sample_interval_hours)
            if batch:
                s.add_all(batch)
                await s.commit()
        except Exception as e:
            _logger.exception(e)
            _logger.error("Hashrate history: Sampling failed")
        finally:
            await release_hashrate_history_lock(s)
    _hashrate_history_updated = True
    _logger.info(f"Hashrate history: Sampling complete, {sample_count} samples committed")


async def acquire_hashrate_history_lock(s):
    try:
        result = await s.execute(text("SELECT pg_try_advisory_lock(123100)"))
        if not result.scalar():
            _logger.info("Hashrate history: waiting for advisory lock")
            await s.execute(text("SELECT pg_advisory_lock(123100)"))
        _logger.debug("Hashrate history: Acquired advisory lock (123100)")
    except Exception as e:
        _logger.exception(e)
        _logger.error("Hashrate history: unable to acquire advisory lock (123100)")
        raise e


async def release_hashrate_history_lock(s):
    await s.execute(text("SELECT pg_advisory_unlock(123100)"))
