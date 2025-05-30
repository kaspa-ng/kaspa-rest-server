# encoding: utf-8
import re
from asyncio import wait_for
from typing import List

from fastapi import Path, HTTPException
from kaspa_script_address import to_script
from pydantic import BaseModel
from starlette.responses import Response

from constants import REGEX_KASPA_ADDRESS, ADDRESS_EXAMPLE
from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client


class OutpointModel(BaseModel):
    transactionId: str = "ef62efbc2825d3ef9ec1cf9b80506876ac077b64b11a39c8ef5e028415444dc9"
    index: int = 0


class ScriptPublicKeyModel(BaseModel):
    scriptPublicKey: str = "20c5629ce85f6618cd3ed1ac1c99dc6d3064ed244013555c51385d9efab0d0072fac"


class UtxoModel(BaseModel):
    amount: str = ("11501593788",)
    scriptPublicKey: ScriptPublicKeyModel
    blockDaaScore: str = "18867232"
    isCoinbase: bool = False


class UtxoResponse(BaseModel):
    address: str = ADDRESS_EXAMPLE
    outpoint: OutpointModel
    utxoEntry: UtxoModel


@app.get(
    "/addresses/{kaspaAddress}/utxos",
    response_model=List[UtxoResponse],
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
async def get_utxos_for_address(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
):
    """
    Lists all open utxo for a given kaspa address
    """
    try:
        to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    utxos = await get_utxos([kaspaAddress])

    ttl = 8
    if len(utxos) > 100_000:
        ttl = 3600
    elif len(utxos) > 10_000:
        ttl = 600
    elif len(utxos) > 1_000:
        ttl = 20

    response.headers["Cache-Control"] = f"public, max-age={ttl}"
    return (utxo for utxo in utxos if utxo["address"] == kaspaAddress)


class UtxoRequest(BaseModel):
    addresses: list[str] = [ADDRESS_EXAMPLE]


@app.post(
    "/addresses/utxos",
    response_model=List[UtxoResponse],
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
async def get_utxos_for_addresses(body: UtxoRequest):
    """
    Lists all open utxo for a given kaspa address
    """
    if body.addresses is None:
        return []

    for kaspaAddress in body.addresses:
        try:
            if not re.search(REGEX_KASPA_ADDRESS, kaspaAddress):
                raise ValueError
            to_script(kaspaAddress)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    return await get_utxos(body.addresses)


async def get_utxos(addresses):
    rpc_client = await kaspad_rpc_client()
    request = {"addresses": addresses}
    if rpc_client:
        utxos = await wait_for(rpc_client.get_utxos_by_addresses(request), 60)
        for utxo in utxos["entries"]:
            spk = utxo["utxoEntry"]["scriptPublicKey"].lstrip("0")
            if len(spk) % 2 == 1:
                spk = "0" + spk
            utxo["utxoEntry"]["scriptPublicKey"] = {"scriptPublicKey": spk}
    else:
        resp = await kaspad_client.request("getUtxosByAddressesRequest", request, timeout=60)
        if resp.get("error"):
            raise HTTPException(500, resp["error"])
        utxos = resp["getUtxosByAddressesResponse"]

    return utxos["entries"]
