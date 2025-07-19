import random
from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states import MainMenu
from keyboards.builder import (
    subscription_keyboard_when_sessions_left
)
from datetime import datetime
from core.persones.persona_behavior import PersonaBehavior
from core.persones.persona_loader import load_personas
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user
from texts.session_texts import (
    NO_USER_TEXT,
    RANDOM_SESSION_STARTED_TEXT
)
from services.session_manager import SessionManager
from core.persones.persona_loader import load_personas

router = Router(name="rnd_session")

# --- Хендлер рандомной сессии - "Случайный клиент" из главного меню ---
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

    # Списание квоты или бонуса
    used, is_free = await session_manager.use_session_quota_or_bonus(session, db_user)
    if not used:
        await callback.message.edit_text(
            "⚠️ Ошибка списания сессии. Попробуйте позже.",
            reply_markup=subscription_keyboard_when_sessions_left()
        )
        return

    # Рандомные значения
    resistance_options = ["средний", "высокий"]
    emotion_options = [
        "тревожный и ранимый", "агрессивный", "холодный и отстранённый",
        "в шоке", "на грани срыва", "поверхностно весёлый"
    ]

    personas = load_personas()
    persona_names = list(personas.keys())
    if not persona_names:
        await callback.message.edit_text("Нет доступных персонажей.")
        return

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
        db_session=session,
        user_id=db_user.id,
        is_free=is_free,
        persona_name=persona_name,
        resistance=resistance,
        emotion=emotion
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