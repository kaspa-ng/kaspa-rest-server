import os

KASPAD_WRPC_URL = os.getenv("KASPAD_WRPC_URL")

USE_SCRIPT_FOR_ADDRESS = os.getenv("USE_SCRIPT_FOR_ADDRESS", "false").lower() == "true"
PREV_OUT_RESOLVED = os.getenv("PREV_OUT_RESOLVED", "false").lower() == "true"

TX_SEARCH_ID_LIMIT = int(os.getenv("TX_SEARCH_ID_LIMIT", "1_000"))
TX_SEARCH_BS_LIMIT = int(os.getenv("TX_SEARCH_BS_LIMIT", "100"))
HEALTH_TOLERANCE_DOWN = int(os.getenv("HEALTH_TOLERANCE_DOWN", "300"))

TRANSACTION_COUNT = os.getenv("TRANSACTION_COUNT", "false").lower() == "true"
ADDRESSES_ACTIVE_COUNT = os.getenv("ADDRESSES_ACTIVE_COUNT", "false").lower() == "true"
HASHRATE_HISTORY = os.getenv("HASHRATE_HISTORY", "false").lower() == "true"
ADDRESS_RANKINGS = os.getenv("ADDRESS_RANKINGS", "false").lower() == "true"
SCRIPTS_UTXOS_LIMIT = int(os.getenv("SCRIPTS_UTXOS_LIMIT", "10000"))

NETWORK_TYPE = os.getenv("NETWORK_TYPE", "mainnet").lower()
BPS = int(os.getenv("BPS", "10"))

SOMPI_PER_KAS = 100_000_000

MAINNET_MAX_SUPPLY_KAS = 28_704_035_605
DEFAULT_MAX_SUPPLY_KAS = 29_000_000_000

MAINNET_CRESCENDO_BS = 108_554_145
DEFAULT_CRESCENDO_BS = 0

match NETWORK_TYPE:
    case "mainnet":
        address_prefix = "kaspa"
        address_example = "kaspa:qqkqkzjvr7zwxxmjxjkmxxdwju9kjs6e9u82uh59z07vgaks6gg62v8707g73"
        max_supply = MAINNET_MAX_SUPPLY_KAS
        crescendo_bs = MAINNET_CRESCENDO_BS
    case "testnet":
        address_prefix = "kaspatest"
        address_example = "kaspatest:qpqz2vxj23kvh0m73ta2jjn2u4cv4tlufqns2eap8mxyyt0rvrxy6ejkful67"
        max_supply = DEFAULT_MAX_SUPPLY_KAS
        crescendo_bs = DEFAULT_CRESCENDO_BS
    case "simnet":
        address_prefix = "kaspasim"
        address_example = "kaspasim:qpqz2vxj23kvh0m73ta2jjn2u4cv4tlufqns2eap8mxyyt0rvrxy6ejkful67"
        max_supply = DEFAULT_MAX_SUPPLY_KAS
        crescendo_bs = DEFAULT_CRESCENDO_BS
    case "devnet":
        address_prefix = "kaspadev"
        address_example = "kaspadev:qpqz2vxj23kvh0m73ta2jjn2u4cv4tlufqns2eap8mxyyt0rvrxy6ejkful67"
        max_supply = DEFAULT_MAX_SUPPLY_KAS
        crescendo_bs = DEFAULT_CRESCENDO_BS
    case _:
        raise ValueError(f"Network type {NETWORK_TYPE} not supported.")

ADDRESS_PREFIX = address_prefix
ADDRESS_EXAMPLE = address_example
MAX_SUPPLY_KAS = max_supply
CRESCENDO_BS = crescendo_bs

REGEX_KASPA_ADDRESS = "^" + ADDRESS_PREFIX + ":[a-z0-9]{61,63}$"

REGEX_DATE = r"^\d{4}-\d{2}-\d{2}$"
REGEX_DATE_OPTIONAL_DAY = r"^\d{4}-\d{2}(-\d{2})?$"

GENESIS_MS = 1636298787842
GENESIS_START_OF_MONTH_MS = 1635724800000  # 2021-11-01
GENESIS_START_OF_DAY_MS = 1636243200000  # 2021-11-07

A_MINUTE_MS = 60 * 1000
AN_HOUR_MS = 60 * A_MINUTE_MS
A_DAY_MS = 24 * AN_HOUR_MS

SUBNETWORK_ID_COINBASE = "0100000000000000000000000000000000000000"
SUBNETWORK_ID_REGULAR = "0000000000000000000000000000000000000000"
