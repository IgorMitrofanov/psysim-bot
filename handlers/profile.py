from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import get_user, get_user_referrals
from keyboards.builder import profile_keyboard, referral_keyboard
from texts.common import profile_text, referral_text, referral_stats_text
from config import logger
from keyboards.builder import main_menu

router = Router(name="profile")


@router.callback_query(lambda c: c.data == "profile")
async def profile_handler(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.message.edit_text("Профиль не найден.")
        return

    user_data = {
        "username": db_user.username or "unknown",
        "telegram_id": db_user.telegram_id,
        "registered_at": db_user.registered_at.strftime("%d.%m.%Y"),
        "active_tariff": (
            "Подписка не оформлена" if db_user.active_tariff == "trial"
            else f"Подписка «{db_user.active_tariff}»"
        ),
        "tariff_expires": db_user.tariff_expires.strftime("%d.%m.%Y") if db_user.tariff_expires else "Не указано",
        "sessions_done": db_user.sessions_done,
        "last_scenario": db_user.last_scenario or "—",
        "bonus_balance": db_user.bonus_balance,
        "balance": db_user.balance,
    }

    await callback.message.edit_text(
        profile_text(user_data),
        reply_markup=profile_keyboard()
    )