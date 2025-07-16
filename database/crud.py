from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models import User, Referral
from sqlalchemy.exc import NoResultFound


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
