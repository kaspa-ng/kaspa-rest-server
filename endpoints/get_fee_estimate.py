# encoding: utf-8
from asyncio import wait_for

from fastapi import HTTPException
from typing import List

from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client
from pydantic import BaseModel


class FeeEstimateBucket(BaseModel):
    feerate: int = 1
    estimatedSeconds: float = 0.004


class FeeEstimateResponse(BaseModel):
    priorityBucket: FeeEstimateBucket
    normalBuckets: List[FeeEstimateBucket]
    lowBuckets: List[FeeEstimateBucket]


@app.get("/info/fee-estimate", response_model=FeeEstimateResponse, tags=["Kaspa network info"])
async def get_fee_estimate():
    """
    Get fee estimate from Kaspad.

    For all buckets, feerate values represent fee/mass of a transaction in `sompi/gram` units.<br>
    Given a feerate value recommendation, calculate the required fee by
    taking the transaction mass and multiplying it by feerate: `fee = feerate * mass(tx)`
    """
    rpc_client = await kaspad_rpc_client()
    if rpc_client:
        fee_estimate = await wait_for(rpc_client.get_fee_estimate(), 10)
    else:
        resp = await kaspad_client.request("getFeeEstimateRequest")
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        fee_estimate = resp["getFeeEstimateResponse"]

    return fee_estimate["estimate"]
