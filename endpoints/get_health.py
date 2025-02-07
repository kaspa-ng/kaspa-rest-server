# encoding: utf-8
import hashlib
from typing import List

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from constants import BPS
from dbsession import async_session
from endpoints.get_virtual_chain_blue_score import current_blue_score_data
from models.Block import Block
from server import app, kaspad_client


class KaspadResponse(BaseModel):
    kaspadHost: str = ""
    serverVersion: str = "0.12.6"
    isUtxoIndexed: bool = True
    isSynced: bool = True
    p2pId: str = "1231312"
    blueScore: int = 101065625


class DBCheckStatus(BaseModel):
    isSynced: bool = True
    blueScore: int | None
    blueScoreDiff: int | None


class HealthResponse(BaseModel):
    kaspadServers: List[KaspadResponse]
    database: DBCheckStatus


@app.get("/info/health", response_model=HealthResponse, tags=["Kaspa network info"])
async def health_state():
    """
    Checks node and database health by comparing blue score and sync status.
    Returns health details or 503 if the database lags by ~10min or no nodes are synced.
    """
    current_blue_score_node = current_blue_score_data.get("blue_score")

    try:
        async with async_session() as s:
            last_blue_score_db = (
                await s.execute(select(Block.blue_score).order_by(Block.blue_score.desc()).limit(1))
            ).scalar()
        if last_blue_score_db is None or current_blue_score_node is None:
            db_check_status = DBCheckStatus(isSynced=False, blueScore=last_blue_score_db)
        else:
            blue_score_diff = abs(current_blue_score_node - last_blue_score_db)
            isSynced = blue_score_diff < 600 * BPS
            db_check_status = DBCheckStatus(
                isSynced=isSynced, blueScore=last_blue_score_db, blueScoreDiff=blue_score_diff
            )
    except Exception:
        db_check_status = DBCheckStatus(isSynced=False)

    await kaspad_client.initialize_all()

    kaspads = [
        {
            "kaspadHost": f"KASPAD_HOST_{i + 1}",
            "serverVersion": kaspad.server_version,
            "isUtxoIndexed": kaspad.is_utxo_indexed,
            "isSynced": kaspad.is_synced,
            "p2pId": hashlib.sha256(kaspad.p2p_id.encode()).hexdigest(),
            "blueScore": current_blue_score_node,
        }
        for i, kaspad in enumerate(kaspad_client.kaspads)
    ]
    result = {
        "kaspadServers": kaspads,
        "database": db_check_status.dict(),
    }

    if not db_check_status.isSynced or not any(kaspad["isSynced"] for kaspad in kaspads):
        raise HTTPException(status_code=503, detail=result)

    return result
