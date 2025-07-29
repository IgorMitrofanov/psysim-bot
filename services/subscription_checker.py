import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from aiogram import Bot
from config import logger
from database.models import User, Tariff, TariffType
from texts.subscription_texts import (
    SUBSCRIPTION_EXPIRED_TEXT,
    SUBSCRIPTION_WILL_EXPIRE_SOON_TEXT
)

async def check_subscriptions_expiry(bot: Bot, db_session_factory: async_sessionmaker):
    """
    Улучшенная фоновая задача для проверки подписок:
    - Проверяет истёкшие подписки
    - Отправляет предупреждения о скором истечении
    - Обрабатывает переход на бесплатный тариф
    """
    while True:
        try:
            async with db_session_factory() as session:
                # 1. Проверка истёкших подписок
                expired_users = await session.execute(
                    select(User)
                    .where(User.active_tariff != TariffType.TRIAL)
                    .where(User.tariff_expires < datetime.utcnow())
                )
                
                for user in expired_users.scalars():
                    await handle_expired_subscription(bot, session, user)
                
                # 2. Проверка подписок, которые скоро истекают (за 1-3 дня)
                soon_expire_users = await session.execute(
                    select(User)
                    .where(User.active_tariff != TariffType.TRIAL)
                    .where(
                        and_(
                            User.tariff_expires > datetime.utcnow(),
                            User.tariff_expires <= datetime.utcnow() + timedelta(days=3),
                            User.subscription_warning_sent == False  # Отправляем только одно уведомление
                        )
                    )
                )
                
                for user in soon_expire_users.scalars():
                    await handle_soon_expire_subscription(bot, session, user)
                
                await session.commit()
                
        except Exception as e:
            logger.error(f"[SUBSCRIPTION] Error in subscription check: {e}")
            await asyncio.sleep(60)  # Короткая пауза при ошибке
        else:
            await asyncio.sleep(3600)  # Обычная пауза - 1 час

async def handle_expired_subscription(bot: Bot, session: AsyncSession, user: User):
    """Обработка истёкшей подписки"""
    logger.info(f"[SUBSCRIPTION] Subscription expired for user {user.telegram_id}")
    
    # Получаем бесплатный тариф
    free_tariff = await session.execute(
        select(Tariff).where(Tariff.name == TariffType.TRIAL)
    )
    free_tariff = free_tariff.scalar_one()
    
    # Обновляем пользователя
    user.active_tariff = TariffType.TRIAL
    user.tariff_expires = None
    user.subscription_warning_sent = False  # Сбрасываем флаг предупреждения
    
    try:
        await bot.send_message(
            user.telegram_id,
            SUBSCRIPTION_EXPIRED_TEXT
        )
        logger.info(f"[SUBSCRIPTION] Notification sent to user {user.telegram_id}")
    except Exception as e:
        logger.error(f"[SUBSCRIPTION] Error sending expiry message to {user.telegram_id}: {e}")

async def handle_soon_expire_subscription(bot: Bot, session: AsyncSession, user: User):
    """Обработка подписки, которая скоро истекает"""
    days_left = (user.tariff_expires - datetime.utcnow()).days
    
    try:
        await bot.send_message(
            user.telegram_id,
            SUBSCRIPTION_WILL_EXPIRE_SOON_TEXT.format(days_left=days_left)
        )
        user.subscription_warning_sent = True  # Помечаем, что уведомление отправлено
        logger.info(f"[SUBSCRIPTION] Warning sent to user {user.telegram_id} ({days_left} days left)")
    except Exception as e:
        logger.error(f"[SUBSCRIPTION] Error sending warning to {user.telegram_id}: {e}")