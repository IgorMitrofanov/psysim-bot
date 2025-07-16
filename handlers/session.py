from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from states import MainMenu
from keyboards.builder import (
    session_resistance_menu,
    session_emotion_menu,
    session_format_menu,
    session_confirm_menu,
    main_menu
)

from texts.session_texts import (
    SESSION_RESISTANCE_SELECT,
    EMOTION_SELECT_TEXT,
    FORMAT_SELECT_TEXT,
    CONFIRM_SESSION_TEXT,
    SESSION_STARTED_TEXT,
    SESSION_ENDED_AHEAD_TEXT,
    NO_USER_TEXT,
    NO_FREE_SESSIONS_TEXT,
)

from texts.common import BACK_TO_MENU_TEXT

from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import get_user
router = Router(name="session")

@router.callback_query(lambda c: c.data == "start_session")
async def start_session_handler(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.message.edit_text(NO_USER_TEXT)
        return

    if db_user.active_tariff == "trial" and db_user.sessions_done >= 1:
        await callback.message.edit_text(NO_FREE_SESSIONS_TEXT)
        return

    await callback.message.edit_text(
        SESSION_RESISTANCE_SELECT,
        reply_markup=session_resistance_menu()
    )
    await state.set_state(MainMenu.session_resistance)


@router.callback_query(MainMenu.session_resistance)
async def session_resistance_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["resistance_medium", "resistance_high"]:
        await state.update_data(resistance=callback.data)
        await callback.message.edit_text(
            EMOTION_SELECT_TEXT, 
            reply_markup=session_emotion_menu()
        )
        await state.set_state(MainMenu.session_emotion)
    elif callback.data == "end_session":
        await callback.message.edit_text(SESSION_ENDED_AHEAD_TEXT)
        await state.clear()
        await callback.message.answer(
            BACK_TO_MENU_TEXT,
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)
        return
    elif callback.data == "back_main":
        await callback.message.edit_text(
            BACK_TO_MENU_TEXT, 
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)


@router.callback_query(MainMenu.session_emotion)
async def session_emotion_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data.startswith("emotion_"):
        await state.update_data(emotion=callback.data)
        await callback.message.edit_text(
            FORMAT_SELECT_TEXT, 
            reply_markup=session_format_menu()
        )
        await state.set_state(MainMenu.session_format)
    elif callback.data == "back_to_resistance":
        await callback.message.edit_text(
            SESSION_RESISTANCE_SELECT, 
            reply_markup=session_resistance_menu()
        )
        await state.set_state(MainMenu.session_resistance)


@router.callback_query(MainMenu.session_format)
async def session_format_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["format_text", "format_audio"]:
        await state.update_data(format=callback.data)
        await callback.message.edit_text(
            CONFIRM_SESSION_TEXT,
            reply_markup=session_confirm_menu()
        )
        await state.set_state(MainMenu.session_confirm)
    elif callback.data == "back_to_emotion":
        await callback.message.edit_text(
            EMOTION_SELECT_TEXT, 
            reply_markup=session_emotion_menu()
        )
        await state.set_state(MainMenu.session_emotion)


@router.callback_query(MainMenu.session_confirm)
async def session_confirm_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    match callback.data:
        case "start_session":
            data = await state.get_data()
            await callback.message.edit_text(SESSION_STARTED_TEXT)
        case "end_session":
            await callback.message.edit_text(SESSION_ENDED_AHEAD_TEXT)
            await state.clear()
            await callback.message.answer(
                BACK_TO_MENU_TEXT, 
                reply_markup=main_menu()
            )
            await state.set_state(MainMenu.choosing)
        case "back_main":
            await callback.message.edit_text(
                BACK_TO_MENU_TEXT, 
                reply_markup=main_menu()
            )
            await state.set_state(MainMenu.choosing)