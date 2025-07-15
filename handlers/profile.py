from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from keyboards.builder import profile_keyboard, referral_keyboard
from texts.common import profile_text, referral_text
from keyboards.builder import main_menu

router = Router()

@router.callback_query(lambda c: c.data == "profile")
async def profile_handler(callback: types.CallbackQuery, state: FSMContext):
    user_data = {
        "username": callback.from_user.username or "unknown",
        "telegram_id": callback.from_user.id,
        "registered_at": "10 мая 2025",
        "active_tariff": "Подписка \"Безлимит на 30 дней\"",
        "tariff_expires": "17 июля 2025",
        "sessions_done": 14,
        "last_scenario": "Границы / Высокое сопротивление",
    }
    await callback.message.edit_text(
        profile_text(user_data), 
        reply_markup=profile_keyboard()
    )

@router.callback_query(lambda c: c.data == "referral")
async def referral_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        referral_text(), 
        reply_markup=referral_keyboard()
    )

@router.callback_query(lambda c: c.data in ["copy_referral_link", "my_referrals", "how_referral_works"])
async def referral_submenu_handler(callback: types.CallbackQuery):
    texts = {
        "copy_referral_link": "📎 Ссылка скопирована в буфер обмена (заглушка).",
        "my_referrals": "📊 Список приглашённых (заглушка).",
        "how_referral_works": "❓ Пояснение, как работает партнёрка (заглушка).",
    }
    await callback.answer(texts[callback.data], show_alert=True)