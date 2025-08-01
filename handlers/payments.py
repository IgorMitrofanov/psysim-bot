from aiogram import Router, types, Bot, F
from aiogram.filters import Command
from aiogram.types import (
    LabeledPrice, 
    PreCheckoutQuery,
    SuccessfulPayment,
    Message
)
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Tariff, Order, TariffType
from database.crud import get_user
from services.referral_manager import process_referral_bonus_after_payment
from config import config, logger
import json
import datetime
from sqlalchemy import select
from aiogram.fsm.state import State, StatesGroup
from texts.subscription_texts import get_tariff_menu_text
from keyboards.builder import profile_keyboard, subscription_keyboard

router = Router(name="payments")

class PaymentStates(StatesGroup):
    WAITING_PAYMENT = State()

@router.callback_query(lambda c: c.data == "buy")
async def buy_tariff_menu(callback: types.CallbackQuery, session: AsyncSession):
    """Меню выбора тарифов с кнопками покупки"""
    
    await callback.message.edit_text(
        await get_tariff_menu_text(session),
        reply_markup=await subscription_keyboard(session),
        parse_mode="HTML"
    )

@router.callback_query(lambda c: c.data.startswith("buy_tariff_"))
async def buy_tariff_with_payment(
    callback: types.CallbackQuery, 
    session: AsyncSession,
    state: FSMContext,
    bot: Bot
):
    """Обработчик покупки тарифа через платежную систему"""
    try:
        tariff_key = callback.data.removeprefix("buy_tariff_")
        
        try:
            tariff_enum = TariffType(tariff_key)
        except ValueError:
            logger.warning(f"Invalid tariff key: {tariff_key}")
            await callback.answer("Неизвестный тариф", show_alert=True)
            return

        tariff = await session.execute(
            select(Tariff)
            .where(Tariff.name == tariff_enum)
            .where(Tariff.is_active == True)
        )
        tariff = tariff.scalar_one_or_none()
        
        if not tariff:
            logger.warning(f"Tariff not found: {tariff_key}")
            await callback.answer("Тариф не найден", show_alert=True)
            return

        # Проверяем, не пытается ли пользователь купить тот же тариф
        user = await get_user(session, telegram_id=callback.from_user.id)
        if user and user.active_tariff == tariff_enum and user.tariff_expires > datetime.datetime.utcnow():
            days_left = (user.tariff_expires - datetime.datetime.utcnow()).days
            await callback.answer(
                f"У вас уже активен этот тариф! Осталось {days_left} дней",
                show_alert=True
            )
            return

        # Формируем данные для платежа
        price_rub = tariff.price / 100
        provider_data = config.provider_data_template
        provider_data["receipt"]["items"][0]["description"] = f"Подписка «{tariff.display_name}»"
        provider_data["receipt"]["items"][0]["amount"]["value"] = f"{price_rub:.2f}"
        
        prices = [LabeledPrice(label=tariff.display_name, amount=tariff.price)]
        
        # Сохраняем данные в состоянии
        await state.set_state(PaymentStates.WAITING_PAYMENT)
        await state.update_data(tariff_id=tariff.id, user_id=callback.from_user.id)
        
        # Подсказка для тестового режима
        if config.PROVIDER_TOKEN.split(':')[1] == 'TEST':
            await callback.message.answer(
                "Для тестирования используйте карту:\n"
                "1111 1111 1111 1026\n"
                "12/22, CVC 000"
            )

        # Отправляем счет
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Подписка «{tariff.display_name}»",
            description=f"Доступ на {tariff.duration_days} дней",
            payload=f"tariff_{tariff.id}",
            provider_token=config.PROVIDER_TOKEN,
            currency=config.CURRENCY,
            prices=prices,
            need_phone_number=True,
            send_phone_number_to_provider=True,
            provider_data=json.dumps(provider_data)
        )
        
        await callback.answer()

    except Exception as e:
        logger.error(f"Error in buy_tariff_with_payment: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при формировании платежа", show_alert=True)
        await state.clear()

@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """Подтверждение платежа"""
    try:
        await pre_checkout_query.bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=True
        )
    except Exception as e:
        logger.error(f"Error in process_pre_checkout_query: {e}")

@router.message(F.successful_payment)
async def process_successful_payment(
    message: Message, 
    state: FSMContext,
    session: AsyncSession,
    bot: Bot
):
    """Обработка успешного платежа"""
    try:
        payment = message.successful_payment
        user_id = message.from_user.id
        tariff_id = int(payment.invoice_payload.split('_')[1])
        
        # Получаем тариф
        tariff = await session.execute(
            select(Tariff).where(Tariff.id == tariff_id)
        )
        tariff = tariff.scalar_one_or_none()
        
        if not tariff:
            await message.answer("Ошибка: тариф не найден")
            return

        # Получаем пользователя
        user = await get_user(session, telegram_id=user_id)
        if not user:
            await message.answer("Ошибка: пользователь не найден")
            return

        # Обновляем данные пользователя
        user.active_tariff = TariffType(tariff.name)
        user.tariff_expires = datetime.datetime.utcnow() + datetime.timedelta(days=tariff.duration_days)
        user.subscription_warning_sent = False
        user.last_activity = datetime.datetime.utcnow()

        # Создаем запись о заказе
        order = Order(
            user_id=user.id,
            description=f"Покупка тарифа «{tariff.display_name}» через ЮKassa",
            price=tariff.price,
            date=datetime.datetime.utcnow(),
            tariff_id=tariff.id,
            status="completed",
            external_id=payment.provider_payment_charge_id
        )
        session.add(order)

        # Начисляем реферальные бонусы
        await process_referral_bonus_after_payment(session, user.id, bot)

        await session.commit()

        # Сообщение об успехе
        success_text = (
            f"✅ Платеж на сумму {payment.total_amount / 100} {payment.currency} прошел успешно!\n"
            f"▸ Тариф: {tariff.display_name}\n"
            f"▸ Срок действия: {tariff.duration_days} дней\n"
            f"▸ Сессий доступно: {tariff.session_quota if tariff.session_quota < 999 else 'безлимит'}\n\n"
            f"Теперь вы можете начать новую сессию!"
        )

        await message.answer(success_text, reply_markup=profile_keyboard())
        await state.clear()

    except Exception as e:
        logger.error(f"Error in process_successful_payment: {e}", exc_info=True)
        await message.answer("Произошла ошибка при обработке платежа")
        await session.rollback()
        await state.clear()