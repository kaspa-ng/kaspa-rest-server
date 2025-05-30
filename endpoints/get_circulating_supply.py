# encoding: utf-8
from asyncio import wait_for

from fastapi import HTTPException
from pydantic import BaseModel

from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client
from fastapi.responses import PlainTextResponse


class CoinSupplyResponse(BaseModel):
    circulatingSupply: str = "1000900697580640180"
    maxSupply: str = "2900000000000000000"


@app.get("/info/coinsupply", tags=["Kaspa network info"])
async def get_coinsupply():
    """
    Get $KAS coin supply information
    """
    rpc_client = await kaspad_rpc_client()
    if rpc_client:
        coin_supply = await wait_for(rpc_client.get_coin_supply(), 10)
    else:
        resp = await kaspad_client.request("getCoinSupplyRequest")
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        coin_supply = resp["getCoinSupplyResponse"]

    return {
        "circulatingSupply": coin_supply["circulatingSompi"],
        "maxSupply": coin_supply["maxSompi"],
    }


@app.get("/info/coinsupply/circulating", tags=["Kaspa network info"], response_class=PlainTextResponse)
async def get_circulating_coins(in_billion: bool = False):
    """
    Get circulating amount of $KAS token as numerical value
    """
    coin_supply = await get_coinsupply()
    coins = str(float(coin_supply["circulatingSupply"]) / 100000000)
    if in_billion:
        return str(round(float(coins) / 1000000000, 2))
    else:
        return coins


@app.get("/info/coinsupply/total", tags=["Kaspa network info"], response_class=PlainTextResponse)
async def get_total_coins(in_billion: bool = False):
    """
    Get total amount of $KAS token as numerical value
    """
    return await get_circulating_coins(in_billion)
