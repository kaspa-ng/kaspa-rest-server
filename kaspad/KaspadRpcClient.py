# encoding: utf-8
import logging
from asyncio import wait_for

from kaspa import RpcClient, Resolver

from constants import KASPAD_WRPC_URL, NETWORK_TYPE

_logger = logging.getLogger(__name__)


async def kaspad_rpc_client() -> RpcClient:
    if KASPAD_WRPC_URL:
        use_resolver = KASPAD_WRPC_URL == "resolver"
        if not hasattr(kaspad_rpc_client, "client"):
            network_id = "testnet-10" if NETWORK_TYPE == "testnet" else "mainnet"
            if use_resolver:
                kaspad_rpc_client.client = RpcClient(resolver=Resolver(), network_id=network_id)
            else:
                kaspad_rpc_client.client = RpcClient(url=KASPAD_WRPC_URL)

        if not kaspad_rpc_client.client.is_connected:
            try:
                await wait_for(kaspad_rpc_client.client.connect(), 10 if use_resolver else 5)
                if kaspad_rpc_client.client.is_connected:
                    logging.info(f"Successfully connected to Kaspad ({KASPAD_WRPC_URL})")
            except Exception:
                pass
            if not kaspad_rpc_client.client.is_connected:
                logging.warning(f"Connection to Kaspad ({KASPAD_WRPC_URL}) failed.")

        return kaspad_rpc_client.client
