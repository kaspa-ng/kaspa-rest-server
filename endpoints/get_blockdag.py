# encoding: utf-8
from asyncio import wait_for
from typing import List

from fastapi import HTTPException
from pydantic import BaseModel

from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client


class BlockdagResponse(BaseModel):
    networkName: str = "kaspa-mainnet"
    blockCount: str = "260890"
    headerCount: str = "2131312"
    tipHashes: List[str] = ["78273854a739e3e379dfd34a262bbe922400d8e360e30e3f31228519a334350a"]
    difficulty: float = 3870677677777.2
    pastMedianTime: str = "1656455670700"
    virtualParentHashes: List[str] = ["78273854a739e3e379dfd34a262bbe922400d8e360e30e3f31228519a334350a"]
    pruningPointHash: str = ("5d32a9403273a34b6551b84340a1459ddde2ae6ba59a47987a6374340ba41d5d",)
    virtualDaaScore: str = "19989141"


@app.get("/info/blockdag", response_model=BlockdagResponse, tags=["Kaspa network info"])
async def get_blockdag():
    """
    Get Kaspa BlockDAG information
    """
    rpc_client = await kaspad_rpc_client()
    if rpc_client:
        return await wait_for(rpc_client.get_block_dag_info(), 10)
    else:
        resp = await kaspad_client.request("getBlockDagInfoRequest")
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        return resp["getBlockDagInfoResponse"]
