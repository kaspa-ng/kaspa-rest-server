# encoding: utf-8
import hashlib
from asyncio import wait_for

from fastapi import HTTPException
from pydantic import BaseModel

from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client


class KaspadInfoResponse(BaseModel):
    mempoolSize: str = "1"
    serverVersion: str = "0.12.2"
    isUtxoIndexed: bool = True
    isSynced: bool = True
    p2pIdHashed: str = "36a17cd8644eef34fc7fe4719655e06dbdf117008900c46975e66c35acd09b01"


@app.get("/info/kaspad", response_model=KaspadInfoResponse, tags=["Kaspa network info"])
async def get_kaspad_info():
    """
    Get some information for kaspad instance, which is currently connected.
    """
    rpc_client = await kaspad_rpc_client()
    if rpc_client:
        info = await wait_for(rpc_client.get_info(), 10)
    else:
        resp = await kaspad_client.request("getInfoRequest")
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        info = resp["getInfoResponse"]

    p2p_id = info.pop("p2pId")
    info["p2pIdHashed"] = hashlib.sha256(p2p_id.encode()).hexdigest()
    return info
