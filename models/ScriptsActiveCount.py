from sqlalchemy import Column, Integer, BigInteger

from dbsession import Base


class ScriptsActiveCount(Base):
    __tablename__ = "scripts_active_counts"
    timestamp = Column(BigInteger, primary_key=True)
    count = Column(Integer)
