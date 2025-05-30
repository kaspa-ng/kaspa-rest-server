# encoding: utf-8
import binascii
from kaspa_script_address import to_address

from constants import ADDRESS_PREFIX


def get_miner_payload_from_block(block: dict):
    for tx in block.get("transactions", []):
        if tx["subnetworkId"] == "0100000000000000000000000000000000000000":
            return tx["payload"]


def retrieve_miner_info_from_payload(payload: str):
    parsed_payload = parse_payload(payload)
    return parsed_payload[1], parsed_payload[0]


def parse_payload(payload: str):
    payload_bin = binascii.unhexlify(payload)
    script = payload_bin[19 : 19 + payload_bin[18]].hex()
    info = payload_bin[19 + payload_bin[18] :].decode()
    address = to_address(ADDRESS_PREFIX, script)
    return [address, info]
