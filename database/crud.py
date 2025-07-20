from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .models import User, Referral
from sqlalchemy.exc import NoResultFound
from core.persones.persona_behavior import PersonaBehavior
from database.models import Session

async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_telegram_id_by_user_id(session: AsyncSession, user_id: int) -> int | None:
    stmt = select(User.telegram_id).where(User.id == user_id)
    result = await session.execute(stmt)
    row = result.first()
    return row[0] if row else None

async def get_user_by_referral_code(session: AsyncSession, code: str) -> User | None:
    stmt = select(User).where(User.referral_code == code)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


from sqlalchemy import func

async def get_sessions_month_count(db_session: AsyncSession, user_id: int) -> int:
    """Возвращает количество сессий пользователя в текущем месяце."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count_query = await db_session.execute(
        select(func.count(Session.id)).where(
            Session.user_id == user_id,
            Session.started_at >= month_start
        )
    )
    count = count_query.scalar_one()
    return count or 0


async def count_user_sessions(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(Session).where(Session.user_id == user_id)
    )
    return result.scalar_one()

from datetime import datetime
import json

async def get_user_by_referral_code(session: AsyncSession, code: str) -> User | None:
    """Поиск пользователя по реферальному коду"""
    result = await session.execute(select(User).where(User.referral_code == code))
    return result.scalar_one_or_none()

async def get_user_referrals(session: AsyncSession, inviter_id: int):
    stmt = (
        select(Referral)
        .where(Referral.inviter_id == inviter_id)
        .options(selectinload(Referral.invited_user))  # eager load invited_user
    )
    result = await session.execute(stmt)
    referrals = result.scalars().all()
    return referrals

async def save_session(
    session: AsyncSession,
    user_id: int,
    persona: PersonaBehavior,
    state_data: dict
) -> bool:
    """Сохраняет сессию в БД с полной информацией"""
    session_id = state_data.get("session_id")
    if not session_id:
        return False

    stmt = select(Session).where(
        Session.id == session_id,
        Session.user_id == user_id
    )
    result = await session.execute(stmt)
    db_session = result.scalar_one_or_none()
    
    if not db_session:
        return False
    
    # Сохраняем историю из persona
    user_msgs = [msg['content'] for msg in persona.get_history() if msg['role'] == 'user']
    bot_msgs = [msg['content'] for msg in persona.get_history() if msg['role'] == 'assistant']
    
    db_session.ended_at = datetime.utcnow()
    db_session.is_active = False
    db_session.user_messages = json.dumps(user_msgs, ensure_ascii=False)
    db_session.bot_messages = json.dumps(bot_msgs, ensure_ascii=False)
    db_session.emotional = state_data.get("emotion")
    db_session.resistance_level = state_data.get("resistance")
    db_session.is_free = state_data.get("is_trial", False)
    
    await session.commit()
    return True

async def create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str = None,
    language_code: str = None,
    is_premium: bool = False,
    referred_by_id: int = None,
    referral_code: str = None
) -> User:
    user = User(
        telegram_id=telegram_id,
        username=username,
        language_code=language_code,
        is_premium=is_premium,
        is_new=True,
        referred_by_id=referred_by_id,
        referral_code=referral_code,
    )
    session.add(user)
    await session.commit()
    return user


async def add_bonus_to_user(session: AsyncSession, user_id: int, amount: int = 1):
    user = await get_user_by_id(session, user_id)
    if user:
        user.bonus_balance += amount
        await session.commit()


async def has_user_paid(session: AsyncSession, user_id: int) -> bool:
    # временный метод: считаем, что если у него не "trial", то оплатил
    user = await get_user_by_id(session, user_id)
    return user and user.active_tariff != "trial"


async def get_or_create_referral_relation(session: AsyncSession, invited_id: int, inviter_id: int):
    stmt = select(Referral).where(Referral.invited_user_id == invited_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        referral = Referral(invited_user_id=invited_id, inviter_id=inviter_id)
        session.add(referral)
        await session.commit()

async def add_balance_to_user(session: AsyncSession, user_id: int, amount: int = 1):
    user = await get_user_by_id(session, user_id)
    if user:
        user.balance += amount
        await session.commit()


async def subtract_balance_from_user(session: AsyncSession, user_id: int, amount: int = 1):
    user = await get_user_by_id(session, user_id)
    if user and user.balance >= amount:
        user.balance -= amount
        await session.commit()

