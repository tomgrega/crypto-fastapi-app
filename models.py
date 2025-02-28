from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Date, UniqueConstraint
from database import Base
from sqlalchemy.ext.declarative import declarative_base

class Coins(Base):
    __tablename__ = 'coins'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    coin_name = Column(String, index=True, unique=True)


class Prices(Base):
    __tablename__ = 'prices'
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    date = Column(Date)
    coin_id = Column(Integer, ForeignKey("coins.id"))
    price = Column(Integer)

