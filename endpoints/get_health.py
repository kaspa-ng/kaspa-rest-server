# encoding: utf-8
import hashlib
from typing import List

from pydantic import BaseModel
from sqlalchemy import select

from dbsession import async_session
from models.Block import Block
from server import app, kaspad_client
from endpoints.get_virtual_chain_blue_score import current_blue_score_data


class KaspadResponse(BaseModel):
    kaspadHost: str = ""
    serverVersion: str = "0.12.6"
    isUtxoIndexed: bool = True
    isSynced: bool = True
    p2pId: str = "1231312"


class DBCheckStatus(BaseModel):
    status: str
    message: str
    blueScoreDB: int = None  # holds db blue score if available


class HealthResponse(BaseModel):
    kaspadServers: List[KaspadResponse]
    currentBlueScoreNode: int = None
    currentDBStatus: DBCheckStatus


@app.get("/info/health", response_model=HealthResponse, tags=["Kaspa network info"])
async def health_state():
    """
    Checks the health of the node and database by comparing the latest blue scores from
    both sources. The response includes the sync status, version, and blue score of the node,
    as well as the latest blue score from the database. If the database blue score lags behind
    the node's blue score by 1,000 or more, an "error" status is returned.
    """
    await kaspad_client.initialize_all()

    kaspads = []
    db_check_status = DBCheckStatus(status="valid", message="Database blue score is within range")

    # latest blue score from the node once
    current_blue_score_node = current_blue_score_data.get("blue_score")

    # latest blue score from the database
    try:
        async with async_session() as s:
            last_blue_score_db = (
                await s.execute(select(Block.blue_score).order_by(Block.blue_score.desc()).limit(1))
            ).scalar()

        # check node and database blue scores
        if last_blue_score_db is None:
            db_check_status = DBCheckStatus(status="error", message="No blue score in database")
        elif current_blue_score_node is not None and abs(current_blue_score_node - last_blue_score_db) >= 1000:
            db_check_status = DBCheckStatus(
                status="error",
                message=f"Blue score difference exceeds 1000 blocks (Node: {current_blue_score_node}, DB: {last_blue_score_db})",
            )
        else:
            # If blue score difference is within 1000 blocks, mark as valid
            db_check_status = DBCheckStatus(
                status="valid",
                message="Database blue score is within range",
                blueScoreDB=last_blue_score_db,
            )

    except Exception:
        db_check_status = DBCheckStatus(status="error", message="Database unavailable")

    for i, kaspad_info in enumerate(kaspad_client.kaspads):
        kaspads.append(
            {
                "isSynced": kaspad_info.is_synced,
                "isUtxoIndexed": kaspad_info.is_utxo_indexed,
                "p2pId": hashlib.sha256(kaspad_info.p2p_id.encode()).hexdigest(),
                "kaspadHost": f"KASPAD_HOST_{i + 1}",
                "serverVersion": kaspad_info.server_version,
            }
        )

    return {
        "kaspadServers": kaspads,
        "currentBlueScoreNode": current_blue_score_node,
        "currentDBStatus": db_check_status,
    }
