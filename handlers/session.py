from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states import MainMenu
from keyboards.builder import (
    session_resistance_menu,
    session_emotion_menu,
    session_format_menu,
    session_confirm_menu,
    main_menu,
    persona_selection_menu
)
from datetime import datetime, timedelta
from config import config
from core.persones.persona_behavior import PersonaBehavior
from core.persones.persona_loader import load_personas
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user, save_session
from texts.session_texts import (
    SESSION_RESISTANCE_SELECT,
    EMOTION_SELECT_TEXT,
    FORMAT_SELECT_TEXT,
    CONFIRM_SESSION_TEXT,
    SESSION_STARTED_TEXT,
    SESSION_ENDED_AHEAD_TEXT,
    NO_USER_TEXT,
    NO_FREE_SESSIONS_TEXT,
    RANDOM_SESSION_STARTED_TEXT
)
from texts.common import BACK_TO_MENU_TEXT
from aiogram.types import Message
from services.session_manager import SessionManager
from aiogram.filters import Command

router = Router(name="session")


@router.message(Command("reset_session"))
async def reset_session_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    data = await state.get_data()
    session_id = data.get("session_id")

    if session_id:
        await session_manager.abort_session(message.from_user.id, session, session_id=session_id)
        await message.answer("🔄 Сессия была принудительно завершена.")
    else:
        await message.answer("ℹ️ Активной сессии не найдено.")

    await state.clear()
    await message.answer(BACK_TO_MENU_TEXT, reply_markup=main_menu())
    await state.set_state(MainMenu.choosing)


# --- Обработка сообщений во время сессии ---
@router.message(MainMenu.in_session)
async def session_interaction_handler(
    message: types.Message, 
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    data = await state.get_data()
    persona: PersonaBehavior = data.get("persona")
    if not persona:
        await message.answer("Ошибка: персонаж не найден.")
        return

    # Проверяем, активна ли еще сессия
    if not await session_manager.is_session_active(message.from_user.id, session):
        await message.answer("⌛️ Время сессии истекло. Сессия сохранена.")
        await message.answer(BACK_TO_MENU_TEXT, reply_markup=main_menu())
        await state.clear()
        await state.set_state(MainMenu.choosing)
        return

    # Добавляем сообщение пользователя в историю
    await session_manager.add_message_to_history(
        message.from_user.id,
        message.text,
        is_user=True
    )

    # Обработка сообщения
    response = await persona.send(message.text)
    await message.answer(response)
    
    # Добавляем ответ бота в историю
    await session_manager.add_message_to_history(
        message.from_user.id,
        response,
        is_user=False
    )

@router.callback_query(MainMenu.in_session, lambda c: c.data == "end_session")
async def manual_end_session_handler(
    callback: types.CallbackQuery, 
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    data = await state.get_data()
    session_id = data.get("session_id")
    
    if session_id:
        await session_manager.end_session(callback.from_user.id, session_id, session)
    
    await callback.message.edit_text(SESSION_ENDED_AHEAD_TEXT)
    await state.clear()
    await callback.message.answer(
        BACK_TO_MENU_TEXT,
        reply_markup=main_menu()
    )
    await state.set_state(MainMenu.choosing)

# --- Старт сессии ---
@router.callback_query(lambda c: c.data == "main_start_session")
async def main_start_session_handler(
    callback: types.CallbackQuery, 
    state: FSMContext, 
    session: AsyncSession,
    session_manager
):
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

# --- Подтверждение сессии ---
@router.callback_query(MainMenu.session_confirm)
async def session_confirm_handler(
    callback: types.CallbackQuery, 
    state: FSMContext, 
    session: AsyncSession,
    session_manager
):
    await callback.answer()
    match callback.data:
        case "session_confirm_start":
            data = await state.get_data()
            persona_name = data.get("persona_name")
            personas = load_personas()
            persona_data = personas.get(persona_name)
            if not persona_data:
                await callback.message.edit_text("Персонаж не найден. Попробуйте снова.")
                await state.set_state(MainMenu.session_format)
                return

            persona = PersonaBehavior(persona_data)
            res_map = {
                "resistance_medium": "средний",
                "resistance_high": "высокий"
            }
            emo_map = {
                "emotion_anxious": "тревожный и ранимый",
                "emotion_aggressive": "агрессивный",
                "emotion_cold": "холодный и отстранённый",
                "emotion_shocked": "в шоке",
                "emotion_breakdown": "на грани срыва",
                "emotion_superficial": "поверхностно весёлый"
            }
            format_map = {
                            "format_text": "Текст",
                            "format_audio": "Аудио"
                        }
            resistance_raw = data.get("resistance")
            emotion_raw = data.get("emotion")
            format_raw = data.get("format")
            
            res_lvl =res_map.get(resistance_raw)
            emo_lvl = emo_map.get(emotion_raw)
            format = format_map.get(format_raw)
            
            persona.reset(
                resistance_level=res_lvl,
                emotional_state=emo_lvl,
                format=format
            )
            
            # Создаем сессию в БД
            session_id = await session_manager.start_session(
                session,
                callback.from_user.id
            )
            
            await state.update_data(
                persona=persona,
                session_start=datetime.utcnow().isoformat(),
                session_id=session_id,
                resistance=res_lvl,
                emotion=emo_lvl,
                format=format
            )

            
            
            await callback.message.edit_text(
                SESSION_STARTED_TEXT.format(
                    resistance=res_lvl,
                    emotion=emo_lvl,
                    selected_persona=persona.name,
                    format=format
                )
            )
            await state.set_state(MainMenu.in_session)

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


# --- Выбор сопротивления ---
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
    elif callback.data == "back_main":
        await callback.message.edit_text(
            BACK_TO_MENU_TEXT,
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)


# --- Выбор эмоции ---
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


from core.persones.persona_loader import load_personas

# --- Выбор формата ---
@router.callback_query(MainMenu.session_format)
async def session_format_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["format_text", "format_audio"]:
        await state.update_data(format=callback.data)

        personas = load_personas()
        persona_names = list(personas.keys())

        await callback.message.edit_text(
            "Выберите персонажа для сессии:",
            reply_markup=persona_selection_menu(persona_names)
        )
        await state.set_state(MainMenu.session_persona)

    elif callback.data == "back_to_emotion":
        await callback.message.edit_text(
            EMOTION_SELECT_TEXT,
            reply_markup=session_emotion_menu()
        )
        await state.set_state(MainMenu.session_emotion)


# --- Выбор персонажа ---
@router.callback_query(MainMenu.session_persona)
async def session_persona_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    if callback.data.startswith("persona_"):
        selected_persona = callback.data.replace("persona_", "")
        await state.update_data(persona_name=selected_persona)

        await callback.message.edit_text(
            CONFIRM_SESSION_TEXT + f"\n\n🧍 Персонаж: {selected_persona}",
            reply_markup=session_confirm_menu()
        )
        await state.set_state(MainMenu.session_confirm)

    elif callback.data == "back_to_format":
        await callback.message.edit_text(
            FORMAT_SELECT_TEXT,
            reply_markup=session_format_menu()
        )
        await state.set_state(MainMenu.session_format)

import random

@router.callback_query(lambda c: c.data == "random_session")
async def random_session_handler(
    callback: types.CallbackQuery, 
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.message.edit_text(NO_USER_TEXT)
        return

    if db_user.active_tariff == "trial" and db_user.sessions_done >= 1:
        await callback.message.edit_text(NO_FREE_SESSIONS_TEXT)
        return

    # 🎲 Рандомные значения
    resistance_options = ["средний", "высокий"]
    emotion_options = [
        "тревожный и ранимый",
        "агрессивный",
        "холодный и отстранённый",
        "в шоке",
        "на грани срыва",
        "поверхностно весёлый"
    ]

    personas = load_personas()
    persona_names = list(personas.keys())
    if not persona_names:
        await callback.message.edit_text("Нет доступных персонажей.")
        return

    # ⚙️ Выбираем случайные параметры
    resistance = random.choice(resistance_options)
    emotion = random.choice(emotion_options)
    persona_name = random.choice(persona_names)
    persona_data = personas[persona_name]

    persona = PersonaBehavior(persona_data)
    persona.reset(
        resistance_level=resistance,
        emotional_state=emotion,
        format="Текст"
    )

    # Создаем сессию
    session_id = await session_manager.start_session(
        session,
        callback.from_user.id
    )

    await state.update_data(
        persona=persona,
        session_start=datetime.utcnow().isoformat(),
        session_id=session_id,
        resistance=resistance,
        emotion=emotion,
        format="Текст"
    )

    await callback.message.edit_text(RANDOM_SESSION_STARTED_TEXT)
    
    await state.set_state(MainMenu.in_session)