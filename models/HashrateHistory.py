from sqlalchemy import Column, BigInteger

from dbsession import Base


class HashrateHistory(Base):
    __tablename__ = "hashrate_history"
    blue_score = Column(BigInteger, primary_key=True)
    daa_score = Column(BigInteger)
    timestamp = Column(BigInteger)
    bits = Column(BigInteger)
