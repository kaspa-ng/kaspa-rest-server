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

* KASPAD_HOST1 - host:port (grpc) to a kaspa node, multiple nodes is supported. (default: none)
* SQL_URI - uri to a postgres db (default: postgresql+asyncpg://127.0.0.1:5432)
* SQL_URI_BLOCKS - uri to a postgres db to query for blocks, block_parent and blocks_transactions (default: SQL_URI)
* NETWORK_TYPE - mainnet/testnet/simnet/devnet (default: mainnet)
* BPS - Blocks per second, affects block difficulty calculation (default: 1)
* DISABLE_PRICE - If true /info/price and /info/market-data is disabled (default: false)
* PREV_OUT_RESOLVED - If true transactions_inputs is assumed to have its previous outpoints resolved, see indexer doc (default: false)
* TX_COUNT_LIMIT - adjust the maximum count for transactions/count (default: 0 - unlimited)
* TX_SEARCH_ID_LIMIT - adjust the maximum number of transactionIds for transactions/search (default: 1000)
* TX_SEARCH_BS_LIMIT - adjust the maximum blue score range for transactions/search (default: 100)
* VSPC_REQUEST - If true enables /info/get-vscp-from-block (default: false)
* DEBUG - Enables additional logging (default: false)
