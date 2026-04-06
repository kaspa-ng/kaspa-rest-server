# encoding: utf-8
import logging
import os
import re
from asyncio import wait_for
from typing import List

from fastapi import Path, HTTPException
from kaspa_script_address import to_script, to_address
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.future import select
from starlette.responses import Response

from constants import REGEX_KASPA_ADDRESS, ADDRESS_EXAMPLE, ADDRESS_PREFIX, SCRIPTS_UTXOS_LIMIT, USE_SCRIPT_FOR_ADDRESS
from dbsession import async_session
from kaspad.KaspadRpcClient import kaspad_rpc_client
from models.ScriptUtxoCount import ScriptUtxoCount
from server import app, kaspad_client

_logger = logging.getLogger(__name__)
IS_SQL_DB_CONFIGURED = os.getenv("SQL_URI") is not None
_utxo_count_table_exists: bool | None = None


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


class UtxoRequest(BaseModel):
    addresses: list[str] = [ADDRESS_EXAMPLE]


class UtxoCountResponse(BaseModel):
    count: int


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
    Lists all open utxo for a given kaspa address.

    Returns an empty list if the address holds too many UTXOs.
    """
    try:
        to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    over_limit = await _get_over_limit_addresses([kaspaAddress])
    if over_limit:
        _logger.info("UTXO count over limit for address: %s", kaspaAddress)
        response.headers["Cache-Control"] = "public, max-age=60"
        return []

    utxos = await get_utxos([kaspaAddress])

    utxo_count = len(utxos)
    if utxo_count > 1_000:
        _logger.info("High UTXO count for address %s: %d", kaspaAddress, utxo_count)

    response.headers["Cache-Control"] = f"public, max-age={_utxo_count_to_ttl(utxo_count)}"
    return (utxo for utxo in utxos if utxo["address"] == kaspaAddress)


@app.post(
    "/addresses/utxos",
    response_model=List[UtxoResponse],
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
async def get_utxos_for_addresses(body: UtxoRequest):
    """
    Lists all open utxo for a given list of kaspa addresses.

    Addresses that hold too many UTXOs are silently omitted from the response.
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

    over_limit = await _get_over_limit_addresses(body.addresses)
    if over_limit:
        _logger.info("UTXO count over limit for addresses: %s", over_limit)
    allowed = [a for a in body.addresses if a not in over_limit]
    if not allowed:
        return []

    utxos = await get_utxos(allowed)
    for addr in allowed:
        addr_count = len([u for u in utxos if u["address"] == addr])
        if addr_count > 1_000:
            _logger.info("High UTXO count for address %s: %d", addr, addr_count)
    return utxos


@app.get(
    "/addresses/{kaspaAddress}/utxos/count",
    response_model=UtxoCountResponse,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
async def get_utxo_count_for_address(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
):
    """
    Returns the number of open UTXOs for a given kaspa address
    """
    try:
        to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    utxo_count = await _get_utxo_count_from_table(kaspaAddress)
    if utxo_count is None:
        utxos = await get_utxos([kaspaAddress])
        utxo_count = len([u for u in utxos if u["address"] == kaspaAddress])
    if utxo_count > 1_000:
        _logger.info("High UTXO count for address %s: %d", kaspaAddress, utxo_count)

    response.headers["Cache-Control"] = f"public, max-age={_utxo_count_to_ttl(utxo_count)}"
    return {"count": utxo_count}


def _utxo_count_to_ttl(count: int) -> int:
    if count > 100_000:
        return 3600
    if count > 10_000:
        return 600
    if count > 1_000:
        return 60
    return 8


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


async def _ensure_table_known(session) -> bool:
    """Checks and caches whether script_utxo_counts exists. Returns table existence."""
    global _utxo_count_table_exists
    if _utxo_count_table_exists is None:
        result = await session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'script_utxo_counts'"
                ");"
            )
        )
        _utxo_count_table_exists = result.scalar()
        if _utxo_count_table_exists:
            _logger.info("script_utxo_counts helper table detected")
        else:
            _logger.info("script_utxo_counts helper table NOT found – UTXO count limiting disabled")
    return _utxo_count_table_exists


async def _get_over_limit_addresses(addresses: list[str]) -> set[str]:
    """
    Returns the subset of *addresses* whose UTXO count exceeds SCRIPTS_UTXOS_LIMIT
    according to the script_utxo_counts table.  Returns an empty set when the table
    does not exist or the primary DB is not configured.
    """
    if not IS_SQL_DB_CONFIGURED:
        return set()

    async with async_session() as s:
        if not await _ensure_table_known(s):
            return set()

        if USE_SCRIPT_FOR_ADDRESS:
            result = await s.execute(
                select(ScriptUtxoCount.script_public_key).where(
                    ScriptUtxoCount.script_public_key.in_([to_script(addr) for addr in addresses]),
                    ScriptUtxoCount.count > SCRIPTS_UTXOS_LIMIT,
                )
            )
            return {to_address(ADDRESS_PREFIX, spk) for spk in result.scalars()}
        else:
            result = await s.execute(
                select(ScriptUtxoCount.script_public_key_address).where(
                    ScriptUtxoCount.script_public_key_address.in_(addresses),
                    ScriptUtxoCount.count > SCRIPTS_UTXOS_LIMIT,
                )
            )
            return set(result.scalars())


async def _get_utxo_count_from_table(kaspaAddress: str) -> int | None:
    """
    Returns the UTXO count for *kaspaAddress* from the helper table,
    or None if the table is absent or has no row for the address.
    """
    if not IS_SQL_DB_CONFIGURED:
        return None

    async with async_session() as s:
        if not await _ensure_table_known(s):
            return None

        if USE_SCRIPT_FOR_ADDRESS:
            result = await s.execute(
                select(ScriptUtxoCount.count).where(ScriptUtxoCount.script_public_key == to_script(kaspaAddress))
            )
        else:
            result = await s.execute(
                select(ScriptUtxoCount.count).where(ScriptUtxoCount.script_public_key_address == kaspaAddress)
            )
        return result.scalar()
