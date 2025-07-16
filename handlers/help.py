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

router = Router(name="help")

@router.callback_query(lambda c: c.data.startswith("help"))
async def help_pages_handler(callback: types.CallbackQuery):
    from texts.feedback import (
        HELP_MAIN_TEXT,
        HELP_START_SESSION_TEXT,
        HELP_AFTER_SESSION_TEXT,
        HELP_FAQ_TEXT
    )
    
    await callback.answer()
    match callback.data:
        case "help":
            await callback.message.edit_text(
                HELP_MAIN_TEXT, 
                reply_markup=help_detail_keyboard()
            )
        case "help_start_session":
            await callback.message.edit_text(
                HELP_START_SESSION_TEXT, 
                reply_markup=help_back_keyboard()
            )
        case "help_after_session":
            await callback.message.edit_text(
                HELP_AFTER_SESSION_TEXT, 
                reply_markup=help_back_keyboard()
            )
        case "help_faq":
            await callback.message.edit_text(
                HELP_FAQ_TEXT, 
                reply_markup=help_back_keyboard()
            )
        case _:
            await callback.message.edit_text(
                "🔧 Этот раздел ещё в разработке. Следи за обновлениями!",
                reply_markup=help_back_keyboard()
            )
