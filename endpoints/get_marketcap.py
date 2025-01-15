# encoding: utf-8

from pydantic import BaseModel

from helper import get_kas_price
from server import app, kaspad_client


class MarketCapResponse(BaseModel):
    marketcap: int = 12000132


@app.get("/info/marketcap", response_model=MarketCapResponse | str, tags=["Kaspa network info"])
async def get_marketcap(stringOnly: bool = False):
    """
    Get $KAS price and market cap. Price info is from coingecko.com
    """
    kas_price = await get_kas_price()
    resp = await kaspad_client.request("getCoinSupplyRequest")
    mcap = round(float(resp["getCoinSupplyResponse"]["circulatingSompi"]) / 1e8 * kas_price)

    if not stringOnly:
        return {"marketcap": mcap}
    else:
        if mcap < 1e9:
            return f"{round(mcap / 1e6, 1)}M"
        else:
            return f"{round(mcap / 1e9, 1)}B"
