# encoding: utf-8
import json
import logging
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select

from constants import BPS
from dbsession import async_session_blocks
from endpoints import sql_db_only
from endpoints.get_blockdag import get_blockdag
from endpoints.get_blocks import get_block_from_kaspad
from helper import KeyValueStore
from helper.difficulty_calculation import bits_to_difficulty
from models.Block import Block
from server import app

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


@app.get("/info/hashrate", response_model=HashrateResponse | str, tags=["Kaspa network info"])
async def get_hashrate(stringOnly: bool = False):
    """
    Returns the current hashrate for Kaspa network in TH/s.
    """
    bdi = await get_blockdag()
    hashrate = bdi["difficulty"] * 2 * BPS
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
        bdi = await get_blockdag()
        block_hash = bdi["virtualParentHashes"][0]
        block = await get_block_from_kaspad(block_hash, False, False)
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
