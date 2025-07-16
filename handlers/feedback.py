import logging
from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from states import MainMenu
from keyboards.builder import (
    cancel_feedback_keyboard, 
    back_to_main_keyboard,
    help_detail_keyboard,
    help_back_keyboard,
    feedback_menu
)

router = Router(name="feedback")

@router.callback_query(lambda c: c.data == "feedback_menu")
async def feedback_menu_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💬 Отзывы и предложения\n\n🗣 Нам очень важно твоё мнение!\nВыбери, что хочешь сделать:",
        reply_markup=feedback_menu()
    )

@router.callback_query(lambda c: c.data == "leave_feedback", MainMenu.choosing)
async def leave_feedback_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ Напиши отзыв в ответ на это сообщение или нажми «🔙 Отмена»:",
        reply_markup=cancel_feedback_keyboard()
    )
    await state.update_data(feedback_msg_id=callback.message.message_id)
    await state.set_state(MainMenu.feedback)


@router.callback_query(lambda c: c.data == "suggest_feature", MainMenu.choosing)
async def suggest_feature_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💡 Напиши предложение по улучшению или нажми «🔙 Отмена»:",
        reply_markup=cancel_feedback_keyboard()
    )
    await state.update_data(feedback_msg_id=callback.message.message_id)
    await state.set_state(MainMenu.suggestion)


@router.callback_query(lambda c: c.data == "report_error", MainMenu.choosing)
async def report_error_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "⚠️ Опиши ошибку или нажми «🔙 Отмена»:",
        reply_markup=cancel_feedback_keyboard()
    )
    await state.update_data(feedback_msg_id=callback.message.message_id)
    await state.set_state(MainMenu.error_report)


async def acknowledge_user_feedback(message: types.Message, state: FSMContext, success_text: str):
    data = await state.get_data()
    msg_id = data.get("feedback_msg_id")
    try:
        if msg_id:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text=success_text,
                reply_markup=back_to_main_keyboard()
            )
        await message.delete()
    except Exception as e:
        logging.warning(f"Ошибка при acknowledge: {e}")
    await state.set_state(MainMenu.choosing)

@router.message(MainMenu.feedback)
async def handle_feedback(message: types.Message, state: FSMContext):
    await acknowledge_user_feedback(
        message, state,
        "✅ Спасибо за твой отзыв! Он уже отправлен нашей команде 💛"
    )

@router.message(MainMenu.suggestion)
async def handle_suggestion(message: types.Message, state: FSMContext):
    await acknowledge_user_feedback(
        message, state,
        "🧠 Отличная идея! Мы обязательно её рассмотрим 💫"
    )

@router.message(MainMenu.error_report)
async def handle_error(message: types.Message, state: FSMContext):
    await acknowledge_user_feedback(
        message, state,
        "🚑 Ошибка зафиксирована. Спасибо, что сообщил(а)."
    )


@router.callback_query(lambda c: c.data == "cancel_feedback")
async def cancel_feedback_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("❌ Отменено")
    await callback.message.edit_text(
        "🔙 Возврат в главное меню", 
        reply_markup=back_to_main_keyboard()
    )
    await state.set_state(MainMenu.choosing)