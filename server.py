# encoding: utf-8
import logging
import os
from asyncio import wait_for
from typing import Optional

import fastapi.logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi_utils.tasks import repeat_every
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from constants import KASPAD_WRPC_URL
from dbsession import async_session
from helper.StrictRoute import StrictRoute
from helper.LimitUploadSize import LimitUploadSize
from kaspad.KaspadMultiClient import KaspadMultiClient
from kaspad.KaspadRpcClient import kaspad_rpc_client

fastapi.logger.logger.setLevel(logging.WARNING)

_logger = logging.getLogger(__name__)

app = FastAPI(
    title="Kaspa REST-API server",
    description="This server is to communicate with kaspa network via REST-API",
    version=os.getenv("VERSION") or "tbd",
    contact={"name": "lAmeR1"},
    license_info={"name": "MIT LICENSE"},
)
app.router.route_class = StrictRoute


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.method in ("GET", "HEAD") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "public, max-age=8"
        return response


app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(LimitUploadSize, max_upload_size=200_000)  # ~1MB

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Data-Source", "X-Page-Count", "X-Next-Page-After", "X-Next-Page-Before"],
)

app.add_middleware(CacheControlMiddleware)


class KaspadStatus(BaseModel):
    is_online: bool = False
    is_wrpc: bool = False
    server_version: Optional[str] = None
    is_utxo_indexed: Optional[bool] = None
    is_synced: Optional[bool] = None


class DatabaseStatus(BaseModel):
    is_online: bool = False


class PingResponse(BaseModel):
    kaspad: KaspadStatus = KaspadStatus()
    database: DatabaseStatus = DatabaseStatus()


@app.get("/ping", include_in_schema=False, response_model=PingResponse)
async def ping_server():
    """
    Ping Pong
    """
    result = PingResponse()

    rpc_client = await kaspad_rpc_client()
    if rpc_client:
        result.kaspad.is_wrpc = True
        try:
            info = await wait_for(rpc_client.get_info(), 10)
            result.kaspad.is_online = True
            result.kaspad.server_version = info["serverVersion"]
            result.kaspad.is_utxo_indexed = info["isUtxoIndexed"]
            result.kaspad.is_synced = info["isSynced"]
        except Exception as err:
            _logger.error(f"Kaspad health check failed {str(err)}")

    elif kaspad_client.kaspads:
        try:
            info = await kaspad_client.kaspads[0].request("getInfoRequest")
            result.kaspad.is_online = True
            result.kaspad.server_version = info["getInfoResponse"]["serverVersion"]
            result.kaspad.is_utxo_indexed = info["getInfoResponse"]["isUtxoIndexed"]
            result.kaspad.is_synced = info["getInfoResponse"]["isSynced"]
        except Exception as err:
            _logger.error("Kaspad health check failed %s", err)

    if os.getenv("SQL_URI") is not None:
        async with async_session() as session:
            try:
                await session.execute("SELECT 1")
                result.database.is_online = True
            except Exception as err:
                _logger.error("Database health check failed %s", err)

    if not result.database.is_online or not result.kaspad.is_synced:
        return JSONResponse(status_code=503, content=result.dict())

    return result


kaspad_hosts = []

for i in range(100):
    try:
        kaspad_hosts.append(os.environ[f"KASPAD_HOST_{i + 1}"].strip())
    except KeyError:
        break

if not kaspad_hosts and not KASPAD_WRPC_URL:
    raise Exception("Please set KASPAD_WRPC_URL or KASPAD_HOST_1 environment variable.")

kaspad_client = KaspadMultiClient(kaspad_hosts)


@app.exception_handler(Exception)
async def unicorn_exception_handler(request: Request, exc: Exception):
    await kaspad_client.initialize_all()
    return JSONResponse(
        status_code=500,
        content={
            "message": "Internal server error"
            # "traceback": f"{traceback.format_exception(exc)}"
        },
    )


@app.on_event("startup")
@repeat_every(seconds=60)
async def periodical_blockdag():
    await kaspad_client.initialize_all()
