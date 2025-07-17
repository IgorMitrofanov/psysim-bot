from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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


async def get_user_by_referral_code(session: AsyncSession, code: str) -> User | None:
    stmt = select(User).where(User.referral_code == code)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


from datetime import datetime
import json

async def save_session(session: AsyncSession, user_id: int, persona: PersonaBehavior, state_data: dict):
    started_at = state_data.get("session_start")
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at)

    user_msgs = [msg['content'] for msg in persona.get_history() if msg['role'] == 'user']
    bot_msgs = [msg['content'] for msg in persona.get_history() if msg['role'] == 'assistant']

    db_session = Session(
        user_id=user_id,
        started_at=started_at,
        ended_at=datetime.utcnow(),
        user_messages=json.dumps(user_msgs, ensure_ascii=False),
        bot_messages=json.dumps(bot_msgs, ensure_ascii=False),
        emotional=state_data.get("emotion"),
        resistance_level=state_data.get("resistance"),
        format=state_data.get("format"),
        is_free=(state_data.get("is_trial", False)),  # если нужно
        # report_text — можно заполнить по итогам сессии, если есть
        # tokens_spent — если считаешь
    )

    session.add(db_session)
    await session.commit()

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
        referred_by=referred_by_id,
        referral_code=referral_code,
    )
    session.add(user)
    await session.commit()

    # Создание записи в таблице referrals
    if referred_by_id:
        referral = Referral(
            invited_user_id=user.id,
            inviter_id=referred_by_id,
        )
        session.add(referral)
        await session.commit()

    return user


async def get_referrals_by_user(session: AsyncSession, user_id: int) -> list[Referral]:
    stmt = select(Referral).where(Referral.inviter_id == user_id)
    result = await session.execute(stmt)
    return result.scalars().all()


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
