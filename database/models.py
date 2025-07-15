from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String)
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_new = Column(Boolean, default=True)
    active_tariff = Column(String, default="trial")
    tariff_expires = Column(DateTime)
    
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    description = Column(String)
    price = Column(Integer)