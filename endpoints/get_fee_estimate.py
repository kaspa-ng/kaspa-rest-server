# encoding: utf-8

from fastapi import HTTPException
from typing import List
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
    Get fee estimate from Kaspad
    """
    resp = await kaspad_client.request("getFeeEstimateRequest")
    if resp is None:
        raise HTTPException(status_code=501, detail="Kaspad does not support fee estimate")
    return resp["getFeeEstimateResponse"]["estimate"]
