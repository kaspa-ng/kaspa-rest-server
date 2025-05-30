# encoding: utf-8
import logging
from asyncio import wait_for

from fastapi import HTTPException
from fastapi_utils.tasks import repeat_every
from pydantic import BaseModel

from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client

_logger = logging.getLogger(__name__)
current_blue_score_data = {"blue_score": 0}


class BlueScoreResponse(BaseModel):
    blueScore: int = 260890


@app.get("/info/virtual-chain-blue-score", response_model=BlueScoreResponse, tags=["Kaspa network info"])
async def get_virtual_selected_parent_blue_score():
    """
    Returns the blue score of the sink
    """
    rpc_client = await kaspad_rpc_client()
    if rpc_client:
        return await wait_for(rpc_client.get_sink_blue_score(), 10)
    else:
        resp = await kaspad_client.request("getSinkBlueScoreRequest")
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        return resp["getSinkBlueScoreResponse"]


@app.on_event("startup")
@repeat_every(seconds=5)
async def update_blue_score():
    global current_blue_score_data
    blue_score = await get_virtual_selected_parent_blue_score()
    current_blue_score_data["blue_score"] = int(blue_score["blueScore"])
    logging.debug(f"Updated current_blue_score: {current_blue_score_data['blue_score']}")
