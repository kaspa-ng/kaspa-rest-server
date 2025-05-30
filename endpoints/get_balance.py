# encoding: utf-8
from asyncio import wait_for

from fastapi import Path, HTTPException
from kaspa_script_address.kaspa_script_address import to_script
from pydantic import BaseModel

from constants import ADDRESS_EXAMPLE, REGEX_KASPA_ADDRESS
from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client


class BalanceResponse(BaseModel):
    address: str = ADDRESS_EXAMPLE
    balance: int = 38240000000


@app.get("/addresses/{kaspaAddress}/balance", response_model=BalanceResponse, tags=["Kaspa addresses"])
async def get_balance_from_kaspa_address(
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
):
    """
    Get balance for a given kaspa address
    """
    try:
        to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    rpc_client = await kaspad_rpc_client()
    request = {"address": kaspaAddress}
    if rpc_client:
        balance = await wait_for(rpc_client.get_balance_by_address(request), 10)
    else:
        resp = await kaspad_client.request("getBalanceByAddressRequest", request)
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        balance = resp["getBalanceByAddressResponse"]

    return {"address": kaspaAddress, "balance": balance["balance"]}
