# encoding: utf-8
import asyncio
import re
import time
from enum import Enum
from typing import List

from kaspa_script_address import to_script

from constants import TX_COUNT_LIMIT

from fastapi import Path, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.future import select
from starlette.responses import Response

from constants import ADDRESS_EXAMPLE, REGEX_KASPA_ADDRESS
from dbsession import async_session
from endpoints import sql_db_only
from endpoints.get_transactions import search_for_transactions, TxSearch, TxModel
from models.AddressKnown import AddressKnown
from models.Transaction import TransactionInput, TransactionOutput
from server import app

DESC_RESOLVE_PARAM = (
    "Use this parameter if you want to fetch the TransactionInput previous outpoint details."
    " Light fetches only the adress and amount. Full fetches the whole TransactionOutput and "
    "adds it into each TxInput."
)


class AddressesActiveRequest(BaseModel):
    addresses: list[str] = [ADDRESS_EXAMPLE]


class TxIdResponse(BaseModel):
    address: str
    active: bool


class TransactionCount(BaseModel):
    total: int
    limit_exceeded: bool


class AddressName(BaseModel):
    address: str
    name: str


class PreviousOutpointLookupMode(str, Enum):
    no = "no"
    light = "light"
    full = "full"


@app.post(
    "/addresses/active",
    response_model=List[TxIdResponse],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_addresses_active(addresses_active_request: AddressesActiveRequest):
    """
    This endpoint checks if addresses have had any transaction activity in the past.
    It is specifically designed for HD Wallets to verify historical address activity.
    """
    async with async_session() as s:
        addresses = set(addresses_active_request.addresses)
        script_addresses = set()
        for address in addresses:
            try:
                if not re.search(REGEX_KASPA_ADDRESS, address):
                    raise ValueError
                script_addresses.add(to_script(address))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid address: {address}")

        result = await s.execute(
            select(TransactionInput.previous_outpoint_script).filter(
                TransactionInput.previous_outpoint_script.in_(script_addresses)
            )
        )
        addresses_used = set(result.scalars().all())
        addresses_remaining = script_addresses - addresses_used
        if addresses_remaining:
            result = await s.execute(
                select(TransactionOutput.script_public_key).filter(
                    TransactionOutput.script_public_key.in_(addresses_remaining)
                )
            )
            addresses_used.update(result.scalars().all())

    return [
        TxIdResponse(address=address, active=(to_script(address) in addresses_used))
        for address in addresses_active_request.addresses
    ]


@app.get(
    "/addresses/{kaspaAddress}/transactions-count",
    response_model=TransactionCount,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_transaction_count_for_address(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
):
    """
    Count the number of transactions associated with this address
    """
    try:
        script = to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    if not TX_COUNT_LIMIT:
        q_in = select(func.count()).filter(TransactionInput.previous_outpoint_script == script)
        q_out = select(func.count()).filter(TransactionOutput.script_public_key == script)
    else:
        q_in = select(func.count()).select_from(
            select(1).filter(TransactionInput.previous_outpoint_script == script).limit(TX_COUNT_LIMIT + 1).subquery()
        )
        q_out = select(func.count()).select_from(
            select(1).filter(TransactionOutput.script_public_key == script).limit(TX_COUNT_LIMIT + 1).subquery()
        )
    async with async_session() as s1, async_session() as s2:
        tx_count = (await s1.execute(q_in)).scalar()
        if not TX_COUNT_LIMIT or tx_count < TX_COUNT_LIMIT + 1:
            tx_count += (await s2.execute(q_out)).scalar()

    limit_exceeded = False
    if TX_COUNT_LIMIT and tx_count > TX_COUNT_LIMIT:
        tx_count = TX_COUNT_LIMIT
        limit_exceeded = True
        ttl = 3600
    elif tx_count > 10000:
        ttl = 30
    else:
        ttl = 8

    response.headers["Cache-Control"] = f"public, max-age={ttl}"
    return TransactionCount(total=tx_count, limit_exceeded=limit_exceeded)


@app.get(
    "/addresses/{kaspaAddress}/name",
    response_model=AddressName | None,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_name_for_address(
    response: Response,
    kaspaAddress: str = Path(
        description="Kaspa address as string e.g. kaspa:qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqkx9awp4e",
        regex=REGEX_KASPA_ADDRESS,
    ),
):
    """
    Get the name for an address
    """
    try:
        to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    async with async_session() as s:
        r = (await s.execute(select(AddressKnown).filter(AddressKnown.address == kaspaAddress))).first()

    response.headers["Cache-Control"] = "public, max-age=600"
    if r:
        return AddressName(address=r.AddressKnown.address, name=r.AddressKnown.name)
    else:
        raise HTTPException(
            status_code=404, detail="Address name not found", headers={"Cache-Control": "public, max-age=600"}
        )


@app.get(
    "/addresses/{kaspaAddress}/full-transactions",
    response_model=List[TxModel],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_full_transactions_for_address(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
    limit: int = Query(description="The number of records to get", ge=1, le=500, default=50),
    offset: int = Query(description="The offset from which to get records", ge=0, default=0),
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(default="no", description=DESC_RESOLVE_PARAM),
):
    """
    DEPRECATED, ONLY RETURNS THE FIRST PAGE
    """
    if offset:
        return []
    return await get_full_transactions_for_address_page(
        response, kaspaAddress, limit, 0, 0, fields, resolve_previous_outpoints
    )


@app.get(
    "/addresses/{kaspaAddress}/full-transactions-page",
    response_model=List[TxModel],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_full_transactions_for_address_page(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
    limit: int = Query(
        description="The max number of records to get. "
        "For paging combine with using 'before/after' from oldest previous result. "
        "Use value of X-Next-Page-Before/-After as long as header is present to continue paging. "
        "The actual number of transactions returned for each page can be > limit.",
        ge=1,
        le=500,
        default=50,
    ),
    before: int = Query(
        description="Only include transactions with block time before this (epoch-millis)", ge=0, default=0
    ),
    after: int = Query(
        description="Only include transactions with block time after this (epoch-millis)", ge=0, default=0
    ),
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(default="no", description=DESC_RESOLVE_PARAM),
):
    """
    Get all transactions for a given address from database.
    And then get their related full transaction data
    """
    try:
        script = to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    q_in = (
        select(TransactionInput.transaction_id, TransactionInput.block_time)
        .filter(TransactionInput.previous_outpoint_script == script)
        .limit(limit)
    )
    q_out = (
        select(TransactionOutput.transaction_id, TransactionOutput.block_time)
        .filter(TransactionOutput.script_public_key == script)
        .limit(limit)
    )

    response.headers["X-Page-Count"] = "0"
    if before != 0 and after != 0:
        raise HTTPException(status_code=400, detail="Only one of [before, after] can be present")
    elif before != 0:
        if before <= 1636298787842:  # genesis block_time
            return []
        q_in = q_in.filter(TransactionInput.block_time < before).order_by(TransactionInput.block_time.desc())
        q_out = q_out.filter(TransactionOutput.block_time < before).order_by(TransactionOutput.block_time.desc())
    elif after != 0:
        if after > int(time.time() * 1000) + 3600000:  # now + 1 hour
            return []
        q_in = q_in.filter(TransactionInput.block_time > after).order_by(TransactionInput.block_time.asc())
        q_out = q_out.filter(TransactionOutput.block_time > after).order_by(TransactionOutput.block_time.asc())
    else:
        q_in = q_in.order_by(TransactionInput.block_time.desc())
        q_out = q_out.order_by(TransactionOutput.block_time.desc())

    async with async_session() as s1, async_session() as s2:
        result_inputs, result_outputs = await asyncio.gather(s1.execute(q_in), s2.execute(q_out))
        results = {x.transaction_id: x.block_time for x in result_inputs.all() + result_outputs.all()}
        if not results:
            return []
        results = sorted(results.items(), key=lambda item: item[1], reverse=(after == 0))[:limit]
        newest_block_time = results[0][1]
        oldest_block_time = results[-1][1]
        tx_ids = [tx_id for tx_id, _ in results]

    response.headers["X-Page-Count"] = str(len(tx_ids))
    if len(tx_ids) >= limit:
        response.headers["X-Next-Page-After"] = str(newest_block_time)
        response.headers["X-Next-Page-Before"] = str(oldest_block_time)

    return await search_for_transactions(TxSearch(transactionIds=tx_ids), fields, resolve_previous_outpoints)
