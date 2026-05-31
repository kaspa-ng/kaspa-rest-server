# encoding: utf-8
import asyncio
import logging
from asyncio import wait_for

from fastapi import HTTPException
from pydantic import BaseModel

from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client

_logger = logging.getLogger(__name__)
current_blue_score_data = {"blue_score": 0}


class BlueScoreResponse(BaseModel):
    blueScore: int = 260890


async def _fetch_sink_blue_score_from_node():
    """Fetch the sink blue score directly from the node. Used by the endpoint
    fallback path and by the background refresh loop."""
    rpc_client = await kaspad_rpc_client()
    if rpc_client:
        return await wait_for(rpc_client.get_sink_blue_score(), 10)
    else:
        resp = await kaspad_client.request("getSinkBlueScoreRequest")
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        return resp["getSinkBlueScoreResponse"]


@app.get("/info/virtual-chain-blue-score", response_model=BlueScoreResponse, tags=["Kaspa network info"])
async def get_virtual_selected_parent_blue_score():
    """
    Returns the blue score of the sink. Served from a background-refreshed
    cache (updated every 5s); falls back to a live fetch only if the cache
    hasn't been populated yet.
    """
    cached = current_blue_score_data.get("blue_score")
    if cached:
        return {"blueScore": cached}
    return await _fetch_sink_blue_score_from_node()


@app.on_event("startup")
async def update_blue_score():
    global current_blue_score_data

    async def loop():
        while True:
            try:
                blue_score = await _fetch_sink_blue_score_from_node()
                current_blue_score_data["blue_score"] = int(blue_score["blueScore"])
                logging.debug(f"Updated current_blue_score: {current_blue_score_data['blue_score']}")
            except Exception as e:
                logging.exception(f"Error updating blue score: {e}")
            await asyncio.sleep(5)

    asyncio.create_task(loop())
