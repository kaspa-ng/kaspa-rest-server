from sqlalchemy import Column, Integer, BigInteger, SmallInteger

from kaspa_script_address import to_address
from constants import ADDRESS_PREFIX
from dbsession import Base
from helper.PublicKeyType import get_public_key_type
from models.AddressColumn import AddressColumn
from models.type_decorators.HexColumn import HexColumn


class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id = Column(HexColumn, primary_key=True)
    subnetwork_id = Column(SmallInteger)
    hash = Column(HexColumn)
    mass = Column(Integer)
    payload = Column(HexColumn)
    block_time = Column(BigInteger)


class TransactionOutput(Base):
    __tablename__ = "transactions_outputs"
    transaction_id = Column(HexColumn, primary_key=True)
    index = Column(SmallInteger, primary_key=True)
    amount = Column(BigInteger)
    script_public_key = Column(HexColumn)
    _script_public_key_address = Column("script_public_key_address", AddressColumn)

    @property
    def script_public_key_address(self):
        if not self._script_public_key_address:
            return to_address(ADDRESS_PREFIX, self.script_public_key)
        return self._script_public_key_address

    @property
    def script_public_key_type(self):
        return get_public_key_type(self.script_public_key)


class TransactionInput(Base):
    __tablename__ = "transactions_inputs"
    transaction_id = Column(HexColumn, primary_key=True)
    index = Column(SmallInteger, primary_key=True)
    previous_outpoint_hash = Column(HexColumn)
    previous_outpoint_index = Column(SmallInteger)
    signature_script = Column(HexColumn)
    sig_op_count = Column(SmallInteger)
    previous_outpoint_script = Column(HexColumn)
    previous_outpoint_amount = Column(BigInteger)

    @property
    def previous_outpoint_address(self):
        if self.previous_outpoint_script:
            return to_address(ADDRESS_PREFIX, self.previous_outpoint_script)
        return None
