from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime
from enum import Enum as PyEnum

Base = declarative_base()

class TariffType(PyEnum):
    TRIAL = "trial"
    START = "start"
    PRO = "pro"
    UNLIMITED = "unlimited"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String)
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_new = Column(Boolean, default=True)
    active_tariff = Column(Enum(TariffType), default=TariffType.TRIAL)
    tariff_expires = Column(DateTime)
    language_code = Column(String, nullable=True)
    is_premium = Column(Boolean, default=False)
    subscription_warning_sent = Column(Boolean, default=False)
    
    balance = Column(Integer, default=0)

    referred_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # ID пригласившего
    referral_code = Column(String, unique=True, index=True)               # Мой реф. код
    bonus_balance = Column(Integer, default=1)                            # Кол-во бонусов

    # Relationships
    orders = relationship("Order", back_populates="user")
    sessions = relationship("Session", back_populates="user")
    achievements = relationship("Achievement", back_populates="user")
    referrals = relationship("Referral", back_populates="inviter", foreign_keys='Referral.inviter_id')
    admin = relationship("Admin", back_populates="user", uselist=False)
    
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime, default=datetime.datetime.utcnow)
    description = Column(String)
    price = Column(Integer)
    status = Column(String, default="pending")
    external_id = Column(String, nullable=True) 
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=True)

    user = relationship("User", back_populates="orders")
    tariff = relationship("Tariff", back_populates="orders")


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    ended_at = Column(DateTime, nullable=True) 

    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)  # Флаг активности сессии
    
    is_free = Column(Boolean, default=False)
    user_messages = Column(Text, nullable=True)  # Хранить всю переписку пользователя (списки строк)
    bot_messages = Column(Text, nullable=True)   # Хранить все ответы бота

    report_text = Column(Text, nullable=True)  # Итоговый отчёт по сессии (если есть)
    tokens_spent = Column(Integer, nullable=True)  # Если считаешь расход токенов
    
    is_rnd = Column(Boolean, default=False) # Для отслеживания случайная сессия или нет, думаю для ачивок и статистики пригодиться

    emotional = Column(String, nullable=True) 
    resistance_level = Column(String, nullable=True)  # "средний", "высокий"
    persona_name = Column(String, nullable=True) 

    user = relationship("User", back_populates="sessions")
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True)
    persona = relationship("Persona", back_populates="sessions")


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
    invited_user = relationship("User", foreign_keys=[invited_user_id])

class FeedbackType(PyEnum):
    FEEDBACK = "feedback"
    SUGGESTION = "suggestion"
    BUG_REPORT = "bug_report"

class FeedbackStatus(PyEnum):
    NEW = "new"
    REVIEWED = "reviewed"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"

class Feedback(Base):
    __tablename__ = "feedback"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # Кто оставил отзыв
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Тип: feedback/suggestion/bug_report
    type = Column(String, nullable=False)
    text = Column(Text, nullable=False)  # Текст отзыва
    
    # Дополнительные поля для баг-репортов
    error_details = Column(Text, nullable=True)  # Технические детали
    reproduction_steps = Column(Text, nullable=True)  # Шаги воспроизведения
    
    # Статус обработки
    status = Column(String, default=FeedbackStatus.NEW.value)
    admin_notes = Column(Text, nullable=True)  # Заметки админов
    
    # Связи
    user = relationship("User")
    
    
#### ADMIN DB

from sqlalchemy import JSON  # Add this import at the top

class Persona(Base):
    __tablename__ = "personas"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    
    # Basic info
    age = Column(Integer)
    gender = Column(String, nullable=True)
    profession = Column(String, nullable=True)
    appearance = Column(String, nullable=True)
    short_description = Column(String, nullable=True)
    
    # Psychological profile - use JSON for complex structures
    background = Column(Text)
    trauma_history = Column(JSON)  # Changed to JSON field
    current_symptoms = Column(JSON)  # Changed to JSON field
    goal_session = Column(Text)
    tone = Column(JSON)  # Changed to JSON field
    
    # Behavior rules
    behaviour_rules = Column(JSON)  # Changed to JSON field
    interaction_guide = Column(JSON)  # Changed to JSON field
    self_reports = Column(JSON)  # Changed to JSON field
    
    # Special considerations
    escalation = Column(JSON)  # Changed to JSON field
    triggers = Column(JSON)  # Changed to JSON field
    
    # Additional metadata
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.datetime.utcnow)
    
    sessions = relationship("Session", back_populates="persona")
    
    
class Tariff(Base):
    __tablename__ = "tariffs"
    
    id = Column(Integer, primary_key=True)
    name = Column(Enum(TariffType), unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)  # в копейках
    duration_days = Column(Integer, nullable=False)  # Длительность действия тарифа
    session_quota = Column(Integer, nullable=False)  # Количество доступных сессий на квоту
    quota_period_days = Column(Integer, default=30)  # Период квоты в днях
    description = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.datetime.utcnow)
    
    orders = relationship("Order", back_populates="tariff")  # Add this line

class AdminAuthCode(Base):
    __tablename__ = "admin_auth_codes"
    
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, index=True)  # Сам код (например, 6-значный)
    admin_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)  # ID админа
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime)  # Время истечения (created_at + 1 час)
    is_used = Column(Boolean, default=False)
    
    # Связь с пользователем
    admin_user = relationship("User")

class Admin(Base):
    __tablename__ = "admins"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Связь с пользователем
    user = relationship("User", back_populates="admin", uselist=False)