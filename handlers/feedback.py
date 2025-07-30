import logging
from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from states import MainMenu
from keyboards.builder import (
    cancel_feedback_keyboard, 
    back_to_main_keyboard,
    feedback_menu
)
from database.crud import get_user
import datetime

from texts.feedback_texts import (
    FEEDBACK_MENU_TEXT,
    LEAVE_FEEDBACK_TEXT,
    SUGGEST_FEATURE_TEXT,
    REPORT_ERROR_TEXT,
    THANK_YOU_FEEDBACK,
    THANK_YOU_SUGGESTION,
    THANK_YOU_ERROR,
    CANCEL_FEEDBACK_POPUP
)

from database.models import Feedback, FeedbackStatus, FeedbackType

router = Router(name="feedback")

@router.callback_query(lambda c: c.data == "feedback_menu")
async def feedback_menu_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        FEEDBACK_MENU_TEXT,
        reply_markup=feedback_menu()
    )

@router.callback_query(lambda c: c.data == "leave_feedback", MainMenu.choosing)
async def leave_feedback_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        LEAVE_FEEDBACK_TEXT,
        reply_markup=cancel_feedback_keyboard()
    )
    await state.update_data(feedback_msg_id=callback.message.message_id)
    await state.set_state(MainMenu.feedback)


@router.callback_query(lambda c: c.data == "suggest_feature", MainMenu.choosing)
async def suggest_feature_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        SUGGEST_FEATURE_TEXT,
        reply_markup=cancel_feedback_keyboard()
    )
    await state.update_data(feedback_msg_id=callback.message.message_id)
    await state.set_state(MainMenu.suggestion)


@router.callback_query(lambda c: c.data == "report_error", MainMenu.choosing)
async def report_error_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        REPORT_ERROR_TEXT,
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
async def handle_feedback(message: types.Message, state: FSMContext, session: AsyncSession):
    db_user = await get_user(session, telegram_id=message.from_user.id)
    # Сохраняем отзыв в БД
    feedback = Feedback(
        user_id=db_user.id,
        type=FeedbackType.FEEDBACK.value,
        text=message.text,
        status=FeedbackStatus.NEW.value
    )
    db_user.last_activity = datetime.datetime.utcnow()
    session.add(db_user)  # Обновляем последнюю активность пользователя
    session.add(feedback)
    await session.commit()
    
    await acknowledge_user_feedback(
        message, state,
        THANK_YOU_FEEDBACK
    )

@router.message(MainMenu.suggestion)
async def handle_suggestion(message: types.Message, state: FSMContext, session: AsyncSession):
    db_user = await get_user(session, telegram_id=message.from_user.id)
    # Сохраняем предложение в БД
    feedback = Feedback(
        user_id=db_user.id,
        type=FeedbackType.SUGGESTION.value,
        text=message.text,
        status=FeedbackStatus.NEW.value
    )
    db_user.last_activity = datetime.datetime.utcnow()
    session.add(db_user)  # Обновляем последнюю активность пользователя
    session.add(feedback)
    await session.commit()
    
    await acknowledge_user_feedback(
        message, state,
        THANK_YOU_SUGGESTION
    )

@router.message(MainMenu.error_report)
async def handle_error(message: types.Message, state: FSMContext, session: AsyncSession):
    db_user = await get_user(session, telegram_id=message.from_user.id)
    # Сохраняем баг-репорт в БД
    feedback = Feedback(
        user_id=db_user.id,
        type=FeedbackType.BUG_REPORT.value,
        text=message.text,
        status=FeedbackStatus.NEW.value
    )
    db_user.last_activity = datetime.datetime.utcnow()
    session.add(db_user)  # Обновляем последнюю активность пользователя
    session.add(feedback)
    await session.commit()
    
    await acknowledge_user_feedback(
        message, state,
        THANK_YOU_ERROR
    )


@router.callback_query(lambda c: c.data == "cancel_feedback")
async def cancel_feedback_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(CANCEL_FEEDBACK_POPUP)
    await callback.message.edit_text(
        FEEDBACK_MENU_TEXT, 
        reply_markup=feedback_menu()
    )
    await state.set_state(MainMenu.choosing)