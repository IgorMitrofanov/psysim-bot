from aiogram import Router, types, Bot
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user
from database.models import TariffType
from keyboards.builder import subscription_keyboard
from keyboards.builder import profile_keyboard
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from database.models import Tariff
from texts.subscription_texts import (
    get_tariff_menu_text,
    TARIFF_FAIL_FUNDS,
    TARIFF_USER_NOT_FOUND,
    UNKNOWN_TARIFF
)
from config import config, logger
import datetime
from database.models import Order
from services.referral_manager import process_referral_bonus_after_payment

router = Router(name="subscription")


@router.callback_query(lambda c: c.data == "buy")
async def buy_tariff_menu(callback: types.CallbackQuery, session: AsyncSession):
    await callback.message.edit_text(
        await get_tariff_menu_text(session),
        reply_markup=await subscription_keyboard(session),
        parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data.startswith("activate_"))
async def activate_tariff_callback(
    callback: types.CallbackQuery, 
    session: AsyncSession, 
    bot: Bot
):
    """Обработчик активации тарифа с проверками и уведомлениями"""
    try:
        # Получаем идентификатор тарифа из callback
        tariff_key = callback.data.removeprefix("activate_")
        
        try:
            # Преобразуем строку в Enum перед запросом к БД
            tariff_enum = TariffType(tariff_key)
        except ValueError:
            logger.warning(f"Invalid tariff key: {tariff_key}")
            await callback.answer(UNKNOWN_TARIFF, show_alert=True)
            return

        # Получаем тариф из базы данных
        tariff = await session.execute(
            select(Tariff)
            .where(Tariff.name == tariff_enum)  # Используем Enum для сравнения
            .where(Tariff.is_active == True)
        )
        tariff = tariff.scalar_one_or_none()
        
        if not tariff:
            logger.warning(f"Tariff not found: {tariff_key}")
            await callback.answer(UNKNOWN_TARIFF, show_alert=True)
            return

        # Получаем пользователя
        user = await get_user(session, telegram_id=callback.from_user.id)
        if not user:
            await callback.answer(TARIFF_USER_NOT_FOUND, show_alert=True)
            return

        # Проверяем баланс
        if user.balance < tariff.price:
            await callback.answer(TARIFF_FAIL_FUNDS, show_alert=True)
            return

        # Проверяем, не пытается ли пользователь купить тот же тариф
        if user.active_tariff == tariff_enum and user.tariff_expires > datetime.utcnow():
            days_left = (user.tariff_expires - datetime.utcnow()).days
            await callback.answer(
                f"У вас уже активен этот тариф! Осталось {days_left} дней",
                show_alert=True
            )
            return

        # Обновляем данные пользователя
        user.balance -= tariff.price
        user.active_tariff = tariff_enum
        user.tariff_expires = datetime.datetime.utcnow() + datetime.timedelta(days=tariff.duration_days)
        user.subscription_warning_sent = False  # Сбрасываем флаг предупреждения
        user.last_activity = datetime.datetime.utcnow()  # Обновляем последнюю активность

        # Создаем запись о заказе
        order = Order(
            user_id=user.id,
            description=f"Покупка тарифа «{tariff.display_name}»",
            price=tariff.price,
            date=datetime.datetime.utcnow(),
            tariff_id=tariff.id
        )
        session.add(order)

        # Начисляем реферальные бонусы
        await process_referral_bonus_after_payment(session, user.id, bot)

        await session.commit()

        # Формируем сообщение об успехе
        success_text = (
            f"✅ Подписка «{tariff.display_name}» активирована!\n"
            f"▸ Срок действия: {tariff.duration_days} дней\n"
            f"▸ Сессий доступно: {tariff.session_quota if tariff.session_quota < 999 else 'безлимит'}\n"
            f"▸ Списано: {tariff.price / 100} ₽\n\n"
            f"Теперь вы можете начать новую сессию!"
        )

        await callback.message.edit_text(
            success_text,
            reply_markup=profile_keyboard()
        )
        await callback.answer()

        # Логируем успешную покупку
        logger.info(f"User {user.telegram_id} activated tariff {tariff.name}")

    except Exception as e:
        logger.error(f"Error activating tariff: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при обработке запроса", show_alert=True)
        await session.rollback()