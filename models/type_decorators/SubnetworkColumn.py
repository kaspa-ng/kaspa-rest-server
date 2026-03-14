from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import BYTEA


class SubnetworkColumn(TypeDecorator):
    """
    Maps the compact BYTEA subnetwork_id (v21+) to/from a 40-character hex string.

    DB storage (v21+): trailing zero bytes stripped; NULL means native (all zeros).
      NULL         -> "0000000000000000000000000000000000000000"
      b'\x01'      -> "0100000000000000000000000000000000000000"
      b'\x01\x02'  -> "0102000000000000000000000000000000000000"
    """

    impl = BYTEA
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is None:
            return "0000000000000000000000000000000000000000"
        padded = bytes(value).ljust(20, b"\x00")
        return padded.hex()

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        raw = bytes.fromhex(value)
        stripped = raw.rstrip(b"\x00")
        return stripped if stripped else None
