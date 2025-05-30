# encoding: utf-8
from asyncio import wait_for
from typing import List

from fastapi import HTTPException
from kaspa_script_address import to_script
from pydantic import BaseModel

from constants import ADDRESS_EXAMPLE
from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client


class BalancesByAddressEntry(BaseModel):
    address: str = ADDRESS_EXAMPLE
    balance: int = 12451591699


class BalanceRequest(BaseModel):
    addresses: list[str] = [ADDRESS_EXAMPLE]


@app.post("/addresses/balances", response_model=List[BalancesByAddressEntry], tags=["Kaspa addresses"])
async def get_balances_from_kaspa_addresses(body: BalanceRequest):
    """
    Get balances for multiple kaspa addresses
    """
    if not body.addresses:
        return []

    for kaspaAddress in body.addresses:
        try:
            to_script(kaspaAddress)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    rpc_client = await kaspad_rpc_client()
    request = {"addresses": body.addresses}
    if rpc_client:
        balances = await wait_for(rpc_client.get_balances_by_addresses(request), 10)
    else:
        resp = await kaspad_client.request("getBalancesByAddressesRequest", request)
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        balances = resp["getBalancesByAddressesResponse"]

    return balances["entries"]
