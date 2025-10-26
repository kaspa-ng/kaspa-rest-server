# kaspa-rest-server
REST API server for Kaspa written in Python.  

The rest server is designed to operate on the database populated by the [simply-kaspa-indexer](https://github.com/supertypo/simply-kaspa-indexer).  
The latest version of the rest server will always be live here: https://api.kaspa.org  

## Build and run
Any third party integrator which depends on the api should make sure to run their own instance.

### Docker
The easiest way to get going is using the pre-built Docker images. Check out the Docker compose example [here](https://github.com/supertypo/simply-kaspa-indexer).

### From source
You will need to install Python (3.12) as well as poetry first.  
Then:
```shell
poetry install --no-root --no-interaction
export DEBUG=true
export KASPAD_HOST_1=localhost:16110
export SQL_URI=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres
poetry run gunicorn -b 0.0.0.0:8000 -w 4 -k uvicorn.workers.UvicornWorker main:app
```

### Environment variables

* KASPAD_WRPC_URL - ws(s)://host:port (wrpc) to a kaspa node, use 'resolver' to use the Kaspa PNN. (default: none)
* KASPAD_HOST1 - host:port (grpc) to a kaspa node, multiple nodes is supported. (default: none)
* SQL_URI - uri to a postgres db (default: postgresql+asyncpg://127.0.0.1:5432)
* SQL_URI_BLOCKS - uri to a postgres db to query for blocks, block_parent and blocks_transactions (default: SQL_URI)
* SQL_POOL_SIZE - postgres db pool size (default: 15)
* SQL_POOL_MAX_OVERFLOW - postgres db pool max overflow (default: 0)
* SQL_POOL_RECYCLE_SECONDS - postgres db connection ttl (default: 1200)
* HEALTH_TOLERANCE_DOWN - How many seconds behind kaspad the db can be before /info/health reports DOWN (default: 300)
* NETWORK_TYPE - mainnet/testnet/simnet/devnet (default: mainnet)
* BPS - Blocks per second, affects block difficulty/hashrate calculation (default: 10)
* DISABLE_PRICE - If true /info/price and /info/market-data is disabled (default: false)
* USE_SCRIPT_FOR_ADDRESS - If true scripts_transactions will be used for address to tx, see indexer doc (default: false)
* PREV_OUT_RESOLVED - If true tx inputs are assumed populated with sender address, see indexer doc (default: false)
* TX_SEARCH_ID_LIMIT - adjust the maximum number of transactionIds for transactions/search (default: 1000)
* TX_SEARCH_BS_LIMIT - adjust the maximum blue score range for transactions/search (default: 100)
* VSPC_REQUEST - If true enables /info/get-vscp-from-block (default: false)
* TRANSACTION_COUNT - If true (a prepopulated) transactions_counts table will be used to provide /transactions/count/{day_or_month} (default: false)
* ADDRESSES_ACTIVE_COUNT - If true (a prepopulated) scripts_active_counts table will be used to provide /addresses/active/count/{day_or_month} (default: false)
* HASHRATE_HISTORY - If true populates hashrate_history table and enables /info/hashrate/history (default: false)
* ADDRESS_RANKINGS - If true enables /addresses/top,distribution. Requires UTXO exporter. (default: false)
* DEBUG - Enables additional logging (default: false)
