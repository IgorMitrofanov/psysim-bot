from aiogram import Router, types
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user
from keyboards.builder import subscription_keyboard
from keyboards.builder import profile_keyboard
from texts.subscription_texts import (
    TARIFF_MENU_TEXT,
    TARIFF_SUCCESS_TEMPLATE,
    TARIFF_FAIL_FUNDS,
    TARIFF_USER_NOT_FOUND
)
import datetime

router = Router(name="subscription")


@router.callback_query(lambda c: c.data == "buy")
async def buy_tariff_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        TARIFF_MENU_TEXT,
        reply_markup=subscription_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data.startswith("activate_"))
async def activate_tariff_callback(callback: types.CallbackQuery, session: AsyncSession):
    # callback.data: activate_start, activate_pro, activate_unlimited
    tariff_map = {
        "activate_start": ("start", 590, 7),
        "activate_pro": ("pro", 1490, 30),
        "activate_unlimited": ("unlimited", 2490, 30)
    }

    data = callback.data
    if data not in tariff_map:
        await callback.answer("❌ Неизвестный тариф", show_alert=True)
        return

    tariff, cost, days = tariff_map[data]

    user = await get_user(session, telegram_id=callback.from_user.id)
    if not user:
        await callback.answer(TARIFF_USER_NOT_FOUND, show_alert=True)
        return

    if user.balance < cost:
        await callback.answer(TARIFF_FAIL_FUNDS, show_alert=True)
        return

    user.balance -= cost
    user.active_tariff = tariff
    user.tariff_expires = datetime.datetime.utcnow() + datetime.timedelta(days=days)
    await session.commit()

    text = TARIFF_SUCCESS_TEMPLATE.format(tariff=tariff.capitalize(), days=days, cost=cost)
    # Ответить в чат с профилем и клавиатурой профиля
    await callback.message.edit_text(text, reply_markup=profile_keyboard())
    await callback.answer() 