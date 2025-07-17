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

from functools import wraps

router = Router(name="session")

# --- Декоратор для проверки времени сессии ---
def check_session_timeout():
    def decorator(func):
        @wraps(func)
        async def wrapper(event: types.Message | types.CallbackQuery, state: FSMContext, *args, **kwargs):
            data = await state.get_data()
            start_str = data.get("session_start")
            if start_str:
                start_time = datetime.fromisoformat(start_str)
                session_length_minutes = int(config.SESSION_LENGTH_MINUTES or 5)
                if datetime.utcnow() - start_time > timedelta(minutes=session_length_minutes):
                    if isinstance(event, types.CallbackQuery):
                        await event.message.edit_text("⌛️ Время сессии истекло.")
                        await event.message.answer("🔙 Возврат в меню", reply_markup=main_menu())
                    else:
                        await event.answer("⌛️ Время сессии истекло.")
                        await event.answer("🔙 Возврат в меню", reply_markup=main_menu())

                    await state.clear()
                    await state.set_state(MainMenu.choosing)
                    return
            return await func(event, state, *args, **kwargs)
        return wrapper
    return decorator

# --- Обработка сообщений во время сессии ---
@router.message(MainMenu.in_session)
@check_session_timeout()
async def session_interaction_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    persona: PersonaBehavior = data.get("persona")
    if not persona:
        await message.answer("Ошибка: персонаж не найден.")
        return

    # Обработка сообщения
    response = await persona.send(message.text)
    await message.answer(response)


# --- Старт сессии ---
@router.callback_query(lambda c: c.data == "main_start_session")
async def main_start_session_handler(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
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


# --- Выбор сопротивления ---
@router.callback_query(MainMenu.session_resistance)
@check_session_timeout()
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
@check_session_timeout()
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
@check_session_timeout()
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


# --- Подтверждение сессии ---
@router.callback_query(MainMenu.session_confirm)
@check_session_timeout()
async def session_confirm_handler(callback: types.CallbackQuery, state: FSMContext):
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

            resistance_raw = data.get("resistance")
            emotion_raw = data.get("emotion")

            persona.reset(
                resistance_level=res_map.get(resistance_raw, "средний"),
                emotional_state=emo_map.get(emotion_raw, "нейтральное")
            )
            await state.update_data(persona=persona)

            # 🕒 Сохраняем время начала сессии
            await state.update_data(session_start=datetime.utcnow().isoformat())

            format_map = {
                "format_text": "Текст",
                "format_audio": "Аудио"
            }

            await callback.message.edit_text(
                SESSION_STARTED_TEXT.format(
                    resistance=res_map.get(resistance_raw, "средний"),
                    emotion=emo_map.get(emotion_raw, "нейтральное"),
                    format=format_map.get(data.get("format"), "не указан")
                )
            )
            await state.set_state(MainMenu.in_session)
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


# --- Выбор персонажа ---
@router.callback_query(MainMenu.session_persona)
@check_session_timeout()
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
