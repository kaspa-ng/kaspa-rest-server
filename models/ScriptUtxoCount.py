from sqlalchemy import Column, BigInteger, String

from dbsession import Base
from models.type_decorators.HexColumn import HexColumn


class ScriptUtxoCount(Base):
    __tablename__ = "script_utxo_counts"
    script_public_key = Column(HexColumn, primary_key=True)
    script_public_key_address = Column(String)
    count = Column(BigInteger)
