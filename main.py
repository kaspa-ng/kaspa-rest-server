# encoding: utf-8
import logging
import os

from starlette.responses import RedirectResponse

from endpoints import (
    get_balance,
    get_utxos,
    get_blocks,
    get_blockdag,
    get_circulating_supply,
    get_kaspad_info,
    get_fee_estimate,
    get_price,
)
from endpoints.get_address_active import get_addresses_active
from endpoints.get_address_distribution import get_distribution_tiers
from endpoints.get_address_names import get_addresses_names
from endpoints.get_address_top import get_addresses_top
from endpoints.get_address_transactions import get_full_transactions_for_address_page
from endpoints.get_address_transactions_count import get_transaction_count_for_address
from endpoints.get_addresses_active_count import get_addresses_active_count_totals
from endpoints.get_balances import get_balances_from_kaspa_addresses
from endpoints.get_blockreward import get_blockreward
from endpoints.get_halving import get_halving
from endpoints.get_hashrate import (
    get_hashrate,
)
from endpoints.get_hashrate_history import (
    update_hashrate_history,
    create_hashrate_history_table,
    get_hashrate_history,
)
from endpoints.get_health import health_state
from endpoints.get_marketcap import get_marketcap
from endpoints.get_transaction_mass import calculate_transaction_mass
from endpoints.get_transactions import get_transaction
from endpoints.get_transactions_count import get_transaction_count_for_day
from endpoints.get_virtual_chain import get_virtual_chain_transactions
from endpoints.get_virtual_chain_blue_score import (
    get_virtual_selected_parent_blue_score,
)
from endpoints.kaspad_requests.submit_transaction_request import (
    submit_a_new_transaction,
)
from helper import get_kas_market_data
from kaspad.KaspadRpcClient import kaspad_rpc_client
from server import app, kaspad_client

IS_SQL_DB_CONFIGURED = os.getenv("SQL_URI") is not None

print(
    f"Loaded: {get_balance} {get_utxos} {get_blocks} {get_blockdag} {get_circulating_supply} {get_distribution_tiers}"
    f"{get_kaspad_info} {get_fee_estimate} {get_marketcap} {get_hashrate} {get_blockreward} {get_halving} {get_hashrate_history}"
    f"{health_state} {get_transaction} {get_virtual_chain_transactions} {get_full_transactions_for_address_page}"
    f"{get_virtual_selected_parent_blue_score} {get_addresses_active} {get_addresses_names} {get_addresses_top}"
    f"{submit_a_new_transaction} {calculate_transaction_mass} {get_price} {get_balances_from_kaspa_addresses}"
    f"{get_transaction_count_for_address} {get_transaction_count_for_day} {get_addresses_active_count_totals}"
)

if os.getenv("VSPC_REQUEST") == "true":
    from endpoints.get_vspc import get_virtual_selected_parent_chain_from_block

    print(get_virtual_selected_parent_chain_from_block)


@app.on_event("startup")
async def startup():
    # We don't want to mess with the new filler's views!
    # create db if needed
    # if False and IS_SQL_DB_CONFIGURED:
    #     await create_all(drop=False)
    # get kaspad
    await get_kas_market_data()

    # find kaspad before staring webserver
    await kaspad_client.initialize_all()
    await kaspad_rpc_client()

    try:
        await create_hashrate_history_table()
        await update_hashrate_history()
    except Exception:
        pass


@app.get("/", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url="/docs")


logging.basicConfig(
    format="%(asctime)s::%(levelname)s::%(name)s::%(message)s",
    level=logging.DEBUG if os.getenv("DEBUG", False) else logging.INFO,
    handlers=[logging.StreamHandler()],
)

if __name__ == "__main__":
    if os.getenv("DEBUG"):
        import uvicorn

        uvicorn.run(app)
