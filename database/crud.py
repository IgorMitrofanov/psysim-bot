from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .models import User, Referral
from database.models import Session
from sqlalchemy import func


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

async def count_user_sessions(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(Session).where(Session.user_id == user_id)
    )
    return result.scalar_one()

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

async def get_user_sessions(session: AsyncSession, user_id: int) -> list[Session]:
    stmt = (
        select(Session)
        .where(Session.user_id == user_id)
        .order_by(Session.started_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()