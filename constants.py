import os

PREV_OUT_RESOLVED = os.getenv("PREV_OUT_RESOLVED", "false").lower() == "true"

TX_COUNT_LIMIT = int(os.getenv("TX_COUNT_LIMIT", "0"))
TX_SEARCH_ID_LIMIT = int(os.getenv("TX_SEARCH_ID_LIMIT", "1000"))
TX_SEARCH_BS_LIMIT = int(os.getenv("TX_SEARCH_BS_LIMIT", "100"))
HEALTH_TOLERANCE_DOWN = int(os.getenv("HEALTH_TOLERANCE_DOWN", "300"))

NETWORK_TYPE = os.getenv("NETWORK_TYPE", "mainnet").lower()
BPS = int(os.getenv("BPS", "1"))

match NETWORK_TYPE:
    case "mainnet":
        address_prefix = "kaspa"
        address_example = "kaspa:qqkqkzjvr7zwxxmjxjkmxxdwju9kjs6e9u82uh59z07vgaks6gg62v8707g73"
    case "testnet":
        address_prefix = "kaspatest"
        address_example = "kaspatest:qpqz2vxj23kvh0m73ta2jjn2u4cv4tlufqns2eap8mxyyt0rvrxy6ejkful67"
    case "simnet":
        address_prefix = "kaspasim"
        address_example = "kaspasim:qpqz2vxj23kvh0m73ta2jjn2u4cv4tlufqns2eap8mxyyt0rvrxy6ejkful67"
    case "devnet":
        address_prefix = "kaspadev"
        address_example = "kaspadev:qpqz2vxj23kvh0m73ta2jjn2u4cv4tlufqns2eap8mxyyt0rvrxy6ejkful67"
    case _:
        raise ValueError(f"Network type {NETWORK_TYPE} not supported.")

ADDRESS_PREFIX = address_prefix
ADDRESS_EXAMPLE = address_example

REGEX_KASPA_ADDRESS = "^" + ADDRESS_PREFIX + ":[a-z0-9]{61,63}$"
