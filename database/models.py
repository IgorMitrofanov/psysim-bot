from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
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
    language_code = Column(String, nullable=True)
    is_premium = Column(Boolean, default=False)
    
    balance = Column(Integer, default=0)

    sessions_done = Column(Integer, default=0)
    last_scenario = Column(String, nullable=True)

    referred_by = Column(Integer, ForeignKey('users.id'), nullable=True)  # ID пригласившего
    referral_code = Column(String, unique=True, index=True)               # Мой реф. код
    bonus_balance = Column(Integer, default=0)                            # Кол-во бонусов

    # Relationships
    orders = relationship("Order", back_populates="user")
    sessions = relationship("Session", back_populates="user")
    achievements = relationship("Achievement", back_populates="user")
    referrals = relationship("Referral", back_populates="inviter", foreign_keys='Referral.inviter_id')


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime, default=datetime.datetime.utcnow)
    description = Column(String)
    price = Column(Integer)
    status = Column(String, default="pending")
    external_id = Column(String, nullable=True) 

    user = relationship("User", back_populates="orders")


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    is_free = Column(Boolean, default=False)
    user_messages = Column(Text)
    bot_messages = Column(Text)
    report_text = Column(Text)
    tokens_spent = Column(Integer)
    emotial = Column(String) # todo
    resistance_level = Column(String)  # "средний", "высокий"
    format = Column(String)            # "текст", "аудио"

    user = relationship("User", back_populates="sessions")


class Achievement(Base):
    __tablename__ = "achievements"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    badge_code = Column(String)
    awarded_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="achievements")


class Referral(Base):
    __tablename__ = "referrals"
    id = Column(Integer, primary_key=True)
    invited_user_id = Column(Integer, ForeignKey("users.id"), unique=True)   # Кто пришёл
    inviter_id = Column(Integer, ForeignKey("users.id"))                     # Кто пригласил
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)
    has_paid = Column(Boolean, default=False)
    bonus_given = Column(Boolean, default=False)

    inviter = relationship("User", back_populates="referrals", foreign_keys=[inviter_id])
