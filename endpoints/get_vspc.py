# encoding: utf-8
from asyncio import wait_for
from typing import List

from fastapi import HTTPException
from pydantic import BaseModel

from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client


class AcceptedTransactionIdsModel(BaseModel):
    acceptingBlockHash: str = "78c1492fa4c88f3ef1c3b14d3bc228a09fdd49c9b224571924b8e256806a495b"
    acceptedTransactionIds: List[str] = [
        "eb5b16f01d209e036c5b7e2674fb9fd63c4c5b399b1b10d8daef2369c07e676c",
        "2f37c0fb935cfcee07cfe2494453a4899f2415fad77dd2cfc058d9109de52e71",
    ]


class VscpResponse(BaseModel):
    removedChainBlockHashes: List[str] = []
    addedChainBlockHashes: List[str] = []
    acceptedTransactionIds: List[AcceptedTransactionIdsModel]


@app.get("/info/get-vscp-from-block", response_model=VscpResponse, tags=["Kaspa network info"])
async def get_virtual_selected_parent_chain_from_block(startHash: str, includeAcceptedTransactionIds: bool = True):
    """
    GetVirtualSelectedParentChainFromBlockRequestMessage requests the virtual selected parent chain from
    some startHash to this kaspad's current virtual.
    """
    rpc_client = await kaspad_rpc_client()
    request = {"startHash": startHash, "includeAcceptedTransactionIds": includeAcceptedTransactionIds}
    if rpc_client:
        return await wait_for(rpc_client.get_virtual_chain_from_block(request), 60)
    else:
        resp = await kaspad_client.request("getVirtualChainFromBlockRequest", request)
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        return resp["getVirtualChainFromBlockResponse"]
