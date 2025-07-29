import asyncio
from datetime import datetime
from sqlalchemy import select
from database.models import User, TariffType
from sqlalchemy.ext.asyncio import async_sessionmaker
from aiogram import Bot
from config import logger
from texts.subscription_texts import SUBSCRIPTION_EXPIRED_TEXT


async def check_subscriptions_expiry(bot: Bot, db_session_factory: async_sessionmaker):
    """
    Фоновая задача для проверки сроков подписок пользователей.
    Если подписка истекла — деактивирует её и отправляет уведомление.
    """
    while True:
        try:
            async with db_session_factory() as session:
                stmt = select(User).where(User.active_tariff != TariffType.TRIAL)
                result = await session.execute(stmt)
                users: User = result.scalars().all()

                for user in users:
                    if user.tariff_expires and user.tariff_expires < datetime.utcnow():
                        logger.info(f"[SUBSCRIPTION] Subscription has expired: user {user.telegram_id}")
                        user.active_tariff = TariffType.TRIAL
                        user.tariff_expires = None
                        await session.commit()

                        try:
                            await bot.send_message(
                                user.telegram_id, SUBSCRIPTION_EXPIRED_TEXT
                            )
                        except Exception as e:
                            logger.error(f"[SUBSCRIPTION] Ошибка при отправке сообщения: {e}")

        except Exception as e:
            logger.error(f"[SUBSCRIPTION] Error check subsription: {e}")

        await asyncio.sleep(3600)  # Проверка каждый час
