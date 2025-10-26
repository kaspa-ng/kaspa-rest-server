from sqlalchemy import Column, Integer, BigInteger

from dbsession import Base


class TransactionCount(Base):
    __tablename__ = "transactions_counts"
    timestamp = Column(BigInteger, primary_key=True)
    coinbase = Column(Integer)
    regular = Column(Integer)
