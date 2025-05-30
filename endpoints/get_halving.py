# encoding: utf-8
from datetime import datetime, timezone

from pydantic import BaseModel
from starlette.responses import PlainTextResponse

from constants import BPS
from endpoints.get_blockdag import get_blockdag
from helper.deflationary_table import calc_block_reward
from server import app


class HalvingResponse(BaseModel):
    nextHalvingTimestamp: int = 1662837270000
    nextHalvingDate: str = "2022-09-10 19:38:52 UTC"
    nextHalvingAmount: float = 155.123123


@app.get("/info/halving", response_model=HalvingResponse | str, tags=["Kaspa network info"])
async def get_halving(field: str | None = None):
    """
    Returns information about chromatic halving
    """
    bdi = await get_blockdag()
    daa_score = int(bdi["virtualDaaScore"])

    reward_info = calc_block_reward(daa_score)

    next_halving_timestamp = datetime.now(timezone.utc).timestamp() + int(
        (reward_info["daa_next_halving"] - daa_score) / BPS
    )

    if field == "nextHalvingTimestamp":
        return PlainTextResponse(content=str(next_halving_timestamp))

    elif field == "nextHalvingDate":
        return PlainTextResponse(
            content=datetime.utcfromtimestamp(next_halving_timestamp).strftime("%Y-%m-%d %H:%M:%S UTC")
        )

    elif field == "nextHalvingAmount":
        return PlainTextResponse(content=str(reward_info["next"]))

    else:
        return {
            "nextHalvingTimestamp": next_halving_timestamp,
            "nextHalvingDate": datetime.utcfromtimestamp(next_halving_timestamp).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "nextHalvingAmount": str(reward_info["next"]),
        }
