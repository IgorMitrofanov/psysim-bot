from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import Referral, User
from database.crud import (
    create_user,
    get_user_by_referral_code,
    get_user_by_id
)
from datetime import datetime
from aiogram import Bot
from logging import getLogger

logger = getLogger(__name__)


async def process_referral_code(session: AsyncSession, code: str) -> User | None:
    try:
        result = await session.execute(
            select(User).where(User.referral_code == code)
        )
        referrer = result.scalar_one_or_none()
        if referrer:
            logger.info(f"Referrer found: {referrer.telegram_id}")
        else:
            logger.warning(f"Referrer with code {code} not found")
        return referrer
    except Exception as e:
        logger.error(f"Error processing referral: {e}")
        return None


async def generate_unique_referral_code(session: AsyncSession) -> str:
    while True:
        code = str(uuid4())[:8]
        if not await get_user_by_referral_code(session, code):
            return code


async def create_new_user_with_referral(
    session: AsyncSession,
    telegram_user,
    referrer: User | None
) -> User:
    referral_code = await generate_unique_referral_code(session)
    user:User = await create_user(
        session=session,
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        language_code=telegram_user.language_code,
        is_premium=telegram_user.is_premium,
        referred_by_id=referrer.id if referrer else None,
        referral_code=referral_code,
    )
    logger.info(f"New user created: {user.id}")
    return user


async def handle_referral_bonus(session: AsyncSession, new_user: User, referrer: User, bot: Bot):
    try:
        # Проверим, не существует ли уже запись
        existing_referral = await session.execute(
            select(Referral).where(Referral.invited_user_id == new_user.id)
        )
        if existing_referral.scalar_one_or_none() is not None:
            logger.warning(f"Referral relation already exists for user {new_user.id}")
            return

        # Создаем запись о реферале
        referral = Referral(
            invited_user_id=new_user.id,
            inviter_id=referrer.id,
            joined_at=datetime.utcnow(),
            has_paid=False,
            bonus_given=False
        )
        session.add(referral)
        await session.commit()

        # Уведомляем
        username_info = f"@{new_user.username}" if new_user.username else f"пользователь (ID: {new_user.telegram_id})"
        text = (
            "🎉 *Новый реферал!*\n"
            f"По вашей ссылке зарегистрировался: {username_info}\n"
            f"Как только он оформит подписку — вы получите бесплатную сессию!"
        )
        await bot.send_message(chat_id=referrer.telegram_id, text=text, parse_mode="Markdown")
    except Exception as e:
        await session.rollback()
        logger.error(f"Referral bonus error: {e}")

async def process_referral_bonus_after_payment(session: AsyncSession, user_id: int):
    referral_stmt = select(Referral).where(Referral.invited_user_id == user_id)
    referral_result = await session.execute(referral_stmt)
    referral = referral_result.scalar_one_or_none()

    if not referral:
        return

    if referral.bonus_given:
        return  # Уже начислен

    user = await get_user_by_id(session, user_id)
    if not user or user.active_tariff == "trial":
        return  # Не оплатил или не найден

    referrer = await get_user_by_id(session, referral.inviter_id)
    if not referrer:
        return

    referrer.bonus_balance += 1
    referral.has_paid = True
    referral.bonus_given = True

    await session.commit()
