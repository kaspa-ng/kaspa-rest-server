# encoding: utf-8
import calendar
from asyncio import wait_for
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException
from fastapi.params import Path
from kaspa_script_address import to_script
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy import select
from starlette.responses import Response

from constants import (
    ADDRESS_EXAMPLE,
    REGEX_KASPA_ADDRESS,
    ADDRESS_RANKINGS,
    REGEX_DATE_OPTIONAL_DAY,
    GENESIS_START_OF_DAY_MS,
    A_DAY_MS,
    GENESIS_START_OF_MONTH_MS,
    AN_HOUR_MS,
)
from dbsession import async_session
from endpoints import sql_db_only
from kaspad.KaspadRpcClient import kaspad_rpc_client
from models.TopScript import TopScript
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


class AddressBalanceHistory(BaseModel):
    timestamp: int
    amount: int


@app.get(
    "/addresses/{kaspaAddress}/balance/{day_or_month}",
    response_model=List[AddressBalanceHistory],
    tags=["Kaspa addresses"],
    summary="EXPERIMENTAL - EXPECT BREAKING CHANGES: Get balance history for Kaspa addresses",
    description="Get balance history for address, only available for larger addresses.",
    openapi_extra={"strict_query_params": True},
)
@sql_db_only
async def get_balance_history_for_kaspa_address(
    response: Response,
    kaspaAddress: str = Path(description=f"Kaspa address as string e.g. {ADDRESS_EXAMPLE}", regex=REGEX_KASPA_ADDRESS),
    day_or_month: str = Path(pattern=REGEX_DATE_OPTIONAL_DAY),
):
    if not ADDRESS_RANKINGS:
        raise HTTPException(status_code=503, detail="Balance history is disabled")
    try:
        script = to_script(kaspaAddress)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid address: {kaspaAddress}")

    now = datetime.now(tz=timezone.utc)
    now_ms = now.timestamp() * 1000
    response.headers["Cache-Control"] = "public, max-age=300"

    if len(day_or_month) == 10:
        try:
            dt = datetime.strptime(day_or_month, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start_ms = int(dt.timestamp() * 1000)
            if start_ms < GENESIS_START_OF_DAY_MS or start_ms > now_ms:
                return []
            end_ms = start_ms + A_DAY_MS
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid day format: {day_or_month}")
    else:
        try:
            dt = datetime.strptime(day_or_month, "%Y-%m").replace(tzinfo=timezone.utc)
            start_ms = int(dt.timestamp() * 1000)
            _, days_in_month = calendar.monthrange(dt.year, dt.month)
            end_ms = start_ms + days_in_month * A_DAY_MS
            if start_ms < GENESIS_START_OF_MONTH_MS or start_ms > now_ms:
                return []
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid month format: {day_or_month}")

    if end_ms < now_ms - 2 * A_DAY_MS:
        response.headers["Cache-Control"] = "public, max-age=3600"
    elif end_ms < now_ms - 2 * AN_HOUR_MS:
        response.headers["Cache-Control"] = "public, max-age=600"

    async with async_session() as s:
        final_query = (
            select(TopScript.timestamp, TopScript.amount)
            .where(TopScript.script_public_key == script)
            .where(
                and_(
                    TopScript.timestamp >= start_ms,
                    TopScript.timestamp < end_ms,
                )
            )
            .order_by(TopScript.timestamp.desc())
        )

        result = await s.execute(final_query)
        balance_history_tuples = result.all()

    return [AddressBalanceHistory(timestamp=ts, amount=amount) for ts, amount in balance_history_tuples]
