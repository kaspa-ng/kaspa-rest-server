# encoding: utf-8
import time
from enum import Enum
from typing import List
from constants import DISABLE_LIMITS

from fastapi import Path, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import text, func, or_
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
    " Light fetches only the adress and amount. Full fetches the whole TransactionOutput and "
    "adds it into each TxInput."
)


class AddressesActiveRequest(BaseModel):
    addresses: list[str] = [ADDRESS_EXAMPLE]


class TxIdResponse(BaseModel):
    address: str
    active: bool


class TransactionsReceivedAndSpent(BaseModel):
    tx_received: str
    tx_spent: str | None
    # received_amount: int = 38240000000


class TransactionForAddressResponse(BaseModel):
    transactions: List[TransactionsReceivedAndSpent]


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


@app.get(
    "/addresses/{kaspaAddress}/full-transactions",
    response_model=List[TxModel],
    response_model_exclude_unset=True,
    tags=["Kaspa addresses"],
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_full_transactions_for_address(
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
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
        query = text(f"""SELECT subquery.address
                     FROM (VALUES
                           {",".join(["(:a{})".format(i) for i in range(len(addresses_active_request.addresses))])}
                     ) AS subquery (address)
                     LEFT JOIN addresses_transactions t ON subquery.address = t.address
                     WHERE t.address IS NULL""")

        # Create a dictionary to bind the addresses to the query parameters
        params = {
            "a{}".format(i): address.split(":")[1] for i, address in enumerate(addresses_active_request.addresses)
        }

        non_active_addresses = await s.execute(query, params)

    non_active_addresses = [x[0] for x in non_active_addresses.all()]
    return [
        TxIdResponse(address=address, active=(address.split(":")[1] not in non_active_addresses))
        for address in addresses_active_request.addresses
    ]


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
    query = (
        select(TxAddrMapping.transaction_id, TxAddrMapping.block_time)
        .filter(TxAddrMapping.address == kaspaAddress)
        .limit(limit)
    )
    response.headers["X-Page-Count"] = "0"
    if before != 0 and after != 0:
        raise HTTPException(status_code=400, detail="Only one of [before, after] can be present")
    elif before != 0:
        if before <= 1636298787842:  # genesis block_time
            return []
        query = query.filter(TxAddrMapping.block_time < before).order_by(TxAddrMapping.block_time.desc())
    elif after != 0:
        if after > int(time.time() * 1000) + 3600000:  # now + 1 hour
            return []
        query = query.filter(TxAddrMapping.block_time > after).order_by(TxAddrMapping.block_time.asc())
    else:
        query = query.order_by(TxAddrMapping.block_time.desc())

    async with async_session() as s:
        tx_within_limit_before = await s.execute(query)

        tx_ids_and_block_times = [(x.transaction_id, x.block_time) for x in tx_within_limit_before.all()]
        if not tx_ids_and_block_times:
            return []

        tx_ids_and_block_times = sorted(tx_ids_and_block_times, key=lambda x: x[1], reverse=True)
        newest_block_time = tx_ids_and_block_times[0][1]
        oldest_block_time = tx_ids_and_block_times[-1][1]
        tx_ids = {tx_id for tx_id, block_time in tx_ids_and_block_times}
        if len(tx_ids_and_block_times) == limit:
            # To avoid gaps when transactions with the same block_time are at the intersection between pages.
            tx_with_same_block_time = await s.execute(
                select(TxAddrMapping.transaction_id)
                .filter(TxAddrMapping.address == kaspaAddress)
                .filter(
                    or_(TxAddrMapping.block_time == newest_block_time, TxAddrMapping.block_time == oldest_block_time)
                )
            )
            tx_ids.update([x for x in tx_with_same_block_time.scalars().all()])

    response.headers["X-Page-Count"] = str(len(tx_ids))
    if len(tx_ids) >= limit:
        response.headers["X-Next-Page-After"] = str(newest_block_time)
        response.headers["X-Next-Page-Before"] = str(oldest_block_time)

    # Legacy:
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
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
):
    """
    Count the number of transactions associated with this address
    """
    async with async_session() as s:
        if DISABLE_LIMITS:
            result = await s.execute(select(func.count()).filter(TxAddrMapping.address == kaspaAddress))
        else:
            result = await s.execute(
                select(func.count()).select_from(
                    select(1).filter(TxAddrMapping.address == kaspaAddress).limit(100001).subquery()
                )
            )
        tx_count = result.scalar()
        limit_exceeded = False
        ttl = 8
        if not DISABLE_LIMITS:
            if tx_count > 10000:
                tx_count = 10000
                limit_exceeded = True
                ttl = 86400
            elif tx_count > 1000:
                ttl = 30

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
    async with async_session() as s:
        r = (await s.execute(select(AddressKnown).filter(AddressKnown.address == kaspaAddress))).first()

    response.headers["Cache-Control"] = "public, max-age=600"
    if r:
        return AddressName(address=r.AddressKnown.address, name=r.AddressKnown.name)
    else:
        raise HTTPException(
            status_code=404, detail="Address name not found", headers={"Cache-Control": "public, max-age=600"}
        )
