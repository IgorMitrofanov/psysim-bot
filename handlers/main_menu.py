from aiogram import types, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards import (
    main_menu,
    free_session_resistance_menu,
    profile_keyboard,
    referral_keyboard,
    feedback_menu,
    cancel_feedback_keyboard,
    help_detail_keyboard,
    back_to_main_keyboard,
    free_session_emotion_menu,
    free_session_format_menu,
    free_session_confirm_menu,
)
from states import MainMenu
from texts.common import profile_text, referral_text
from texts.feedback import HELP_MAIN_TEXT

router = Router()

@router.callback_query(MainMenu.choosing)
async def handle_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    match callback.data:
        case "start_session":
            await callback.message.edit_text(
                "🧱 Выбор сопротивления клиента",
                reply_markup=free_session_resistance_menu()
            )
            await state.set_state(MainMenu.free_session_resistance)

        case "profile":
            # заглушка
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

        case "referral":
            await callback.message.edit_text(referral_text(), reply_markup=referral_keyboard())

        case "feedback_menu":
            await callback.message.edit_text(
                "💬 Отзывы и предложения\n\n🗣 Нам очень важно твоё мнение!\nВыбери, что хочешь сделать:",
                reply_markup=feedback_menu()
            )

        case "leave_feedback":
            await callback.message.edit_text(
                "✍️ Напиши отзыв в ответ на это сообщение или нажми «🔙 Отмена»:",
                reply_markup=cancel_feedback_keyboard()
            )
            await state.update_data(feedback_msg_id=callback.message.message_id)
            await state.set_state(MainMenu.feedback)

        case "suggest_feature":
            await callback.message.edit_text(
                "💡 Напиши предложение по улучшению или нажми «🔙 Отмена»:",
                reply_markup=cancel_feedback_keyboard()
            )
            await state.update_data(feedback_msg_id=callback.message.message_id)
            await state.set_state(MainMenu.suggestion)

        case "report_error":
            await callback.message.edit_text(
                "⚠️ Опиши ошибку или нажми «🔙 Отмена»:",
                reply_markup=cancel_feedback_keyboard()
            )
            await state.update_data(feedback_msg_id=callback.message.message_id)
            await state.set_state(MainMenu.error_report)

        case "back_main":
            await callback.message.edit_text("🔙 Возврат в главное меню", reply_markup=main_menu())
            await state.set_state(MainMenu.choosing)

        case "help":
            await callback.message.edit_text(HELP_MAIN_TEXT, reply_markup=help_detail_keyboard())

        case _:
            await callback.message.edit_text(
                f"🔧 Заглушка: {callback.data}\n(Функция пока в разработке)",
                reply_markup=main_menu()
            )
