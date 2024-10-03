# encoding: utf-8
import time
from enum import Enum
from typing import List

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
from models.TxAddrMapping import TxAddrMapping
from server import app

DESC_RESOLVE_PARAM = (
    "Use this parameter if you want to fetch the TransactionInput previous outpoint details."
    " Light fetches only the address and amount. Full fetches the whole TransactionOutput and "
    "adds it into each TxInput."
)


class TransactionsReceivedAndSpent(BaseModel):
    tx_received: str
    tx_spent: str | None
    # received_amount: int = 38240000000


class TransactionForAddressResponse(BaseModel):
    transactions: List[TransactionsReceivedAndSpent]


class TransactionCount(BaseModel):
    total: int


class AddressName(BaseModel):
    address: str
    name: str


class PreviousOutpointLookupMode(str, Enum):
    no = "no"
    light = "light"
    full = "full"


@app.get(
    "/addresses/{kaspaAddress}/full-transactions",
    response_model=List[TxModel],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_full_transactions_for_address(
    kaspaAddress: str = Path(
        description="Kaspa address as string e.g. " f"{ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS
    ),
    limit: int = Query(description="The number of records to get", ge=1, le=500, default=50),
    offset: int = Query(description="The offset from which to get records", ge=0, default=0),
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(default="no", description=DESC_RESOLVE_PARAM),
):
    """
    Get all transactions for a given address from database.
    And then get their related full transaction data
    """

    async with async_session() as s:
        # Doing it this way as opposed to adding it directly in the IN clause
        # so I can re-use the same result in tx_list, TxInput and TxOutput
        tx_within_limit_offset = await s.execute(
            select(TxAddrMapping.transaction_id)
            .filter(TxAddrMapping.address == kaspaAddress)
            .limit(limit)
            .offset(offset)
            .order_by(TxAddrMapping.block_time.desc())
        )

        tx_ids_in_page = [x[0] for x in tx_within_limit_offset.all()]

    return await search_for_transactions(TxSearch(transactionIds=tx_ids_in_page), fields, resolve_previous_outpoints)


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
    kaspaAddress: str = Path(
        description="Kaspa address as string e.g. " f"{ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS
    ),
    limit: int = Query(
        description="The max number of records to get. "
        "For paging combine with using 'before' from oldest previous result, "
        "repeat until an **empty** resultset is returned."
        "The actual number of transactions returned can be higher if there are transactions with the same block time at the limit.",
        ge=1,
        le=500,
        default=50,
    ),
    before: int = Query(
        description="Only include transactions with block time before this (epoch-millis)", ge=0, default=0
    ),
    fields: str = "",
    resolve_previous_outpoints: PreviousOutpointLookupMode = Query(default="no", description=DESC_RESOLVE_PARAM),
):
    """
    Get all transactions for a given address from database.
    And then get their related full transaction data
    """

    async with async_session() as s:
        # Doing it this way as opposed to adding it directly in the IN clause
        # so I can re-use the same result in tx_list, TxInput and TxOutput
        before = int(time.time() * 1000) if before == 0 else before
        tx_within_limit_before = await s.execute(
            select(TxAddrMapping.transaction_id, TxAddrMapping.block_time)
            .filter(TxAddrMapping.address == kaspaAddress)
            .filter(TxAddrMapping.block_time < before)
            .limit(limit)
            .order_by(TxAddrMapping.block_time.desc())
        )

        tx_ids_and_block_times = [(x.transaction_id, x.block_time) for x in tx_within_limit_before.all()]
        if not tx_ids_and_block_times:
            return []

        tx_ids = {tx_id for tx_id, block_time in tx_ids_and_block_times}
        oldest_block_time = tx_ids_and_block_times[-1][1]

        if len(tx_ids_and_block_times) == limit:
            # To avoid gaps when transactions with the same block_time are at the boundry between pages.
            # Get the time of the last transaction and fetch additional transactions for the same address and timestamp
            tx_with_same_block_time = await s.execute(
                select(TxAddrMapping.transaction_id)
                .filter(TxAddrMapping.address == kaspaAddress)
                .filter(TxAddrMapping.block_time == oldest_block_time)
            )
            tx_ids.update([x for x in tx_with_same_block_time.scalars().all()])

    response.headers["X-Current-Page"] = str(len(tx_ids))
    response.headers["X-Oldest-Epoch-Millis"] = str(oldest_block_time)

    return await search_for_transactions(TxSearch(transactionIds=list(tx_ids)), fields, resolve_previous_outpoints)


@app.get(
    "/addresses/{kaspaAddress}/transactions-count",
    response_model=TransactionCount,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_transaction_count_for_address(
    kaspaAddress: str = Path(
        description="Kaspa address as string e.g. " f"{ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS
    ),
):
    """
    Count the number of transactions associated with this address
    """

    async with async_session() as s:
        count_query = select(func.count()).filter(TxAddrMapping.address == kaspaAddress)

        tx_count = await s.execute(count_query)

    return TransactionCount(total=tx_count.scalar())


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
        description="Kaspa address as string e.g. "
        "kaspa:qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqkx9awp4e",
        regex=REGEX_KASPA_ADDRESS,
    ),
):
    """
    Get the name for an address
    """
    async with async_session() as s:
        r = (await s.execute(select(AddressKnown).filter(AddressKnown.address == kaspaAddress))).first()

    response.headers["Cache-Control"] = "public, max-age=600"
    if r:
        return AddressName(address=r.AddressKnown.address, name=r.AddressKnown.name)
    else:
        raise HTTPException(
            status_code=404, detail="Address name not found", headers={"Cache-Control": "public, max-age=600"}
        )
