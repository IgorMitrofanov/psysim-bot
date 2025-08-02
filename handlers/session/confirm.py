from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states import MainMenu
from keyboards.builder import (
    session_resistance_menu,
    session_emotion_menu,
    session_confirm_menu,
    main_menu,
    persona_selection_menu,
    subscription_keyboard_when_sessions_left
)
from datetime import datetime
from core.persones.persona_decision_layer import PersonaDecisionLayer
from core.persones.persona_humanization_layer import PersonaHumanizationLayer
from core.persones.persona_instruction_layer import PersonaSalterLayer
from core.persones.persona_response_layer import PersonaResponseLayer
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user
from texts.session_texts import (
    SESSION_RESISTANCE_SELECT,
    EMOTION_SELECT_TEXT,
    CONFIRM_SESSION_TEXT,
    SESSION_STARTED_TEXT,
    NO_USER_TEXT,
    NO_QUOTA_OR_BONUS_FOR_SESSION,
    CHOOSE_PERSONE_FOR_SESSION_TEXT,
    res_map,
    emo_map,
)
from texts.common import BACK_TO_MENU_TEXT
from services.session_manager import SessionManager

router = Router(name="session_confirm")

# --- Старт сессии ---
@router.callback_query(lambda c: c.data == "main_start_session")
async def main_start_session_handler(
    callback: types.CallbackQuery, 
    state: FSMContext, 
    session: AsyncSession
):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.message.edit_text(NO_USER_TEXT)
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
    session_manager: SessionManager
):
    await callback.answer()
    match callback.data:
        # Меню подтверждения: начать сессию, назад
        case "session_confirm_start":
            # Подготовка к началу сессии
            data = await state.get_data()
            persona_name = data.get("persona_name")
            personas = await session_manager.get_all_personas()
            persona_data = personas.get(persona_name)
            if not persona_data:
                await callback.message.edit_text("Персонаж не найден. Попробуйте снова.")
                await state.set_state(MainMenu.session_emotion)
                return
            
            resistance_raw = data.get("resistance")
            emotion_raw = data.get("emotion")
            
            resistance =res_map.get(resistance_raw)
            emotion = emo_map.get(emotion_raw)
            
            # Инициализация 1 слоя ИИ, принятие решений
            decisioner = PersonaDecisionLayer(persona_data, resistance_level=resistance, emotional_state=emotion)
            # Инициализация 2 слоя ИИ, для созданий инструкций для третьей нейросети (инструкции добавляются к сообщением юзера, поэтому "подсолка")
            salter = PersonaSalterLayer(persona_data, resistance_level=resistance, emotional_state=emotion)
            # Инициализация 3 слоя ИИ, для формирования ответов из подсоленных сообщений с инструкциями
            responser = PersonaResponseLayer(persona_data, resistance_level=resistance, emotional_state=emotion)
            # Инициализация 3 слоя ИИ, для хуманизации итогового сообщения
            humanizator = PersonaHumanizationLayer(persona_data, resistance_level=resistance, emotional_state=emotion)
            meta_history = []
            total_tokens = 0

            
            # Получаем юзера из БД
            db_user = await get_user(session, telegram_id=callback.from_user.id)
            if not db_user:
                # Обработка ошибки если он не найден
                await callback.message.edit_text(NO_USER_TEXT)
                return

            # Пытаемся списать квоту или бонус
            used, is_free = await session_manager.use_session_quota_or_bonus(session, db_user.id)
            if not used:
                # Предлагаем купить, если нет ресурсов на сессию
                await callback.message.answer(
                    NO_QUOTA_OR_BONUS_FOR_SESSION,
                    reply_markup=await subscription_keyboard_when_sessions_left(session)
                )
                return
            
            # Делегируем менеджеру сессий начать сессию, и запрашиваем у него ее айди
            session_id = await session_manager.start_session(
                db_session=session,
                user_id=db_user.id,
                is_free=is_free,
                persona_name=persona_name,
                resistance=resistance,
                emotion=emotion
            )
            # Обновляем данные в стейт
            await state.update_data(
                session_start=datetime.utcnow().isoformat(),
                session_id=session_id,
                user_id=db_user.id,
                resistance=resistance,
                emotion=emotion,
                decisioner=decisioner.to_dict(),
                responser=responser.to_dict(),
                meta_history=meta_history,
                salter=salter.to_dict(),
                humanizator=humanizator.to_dict(),
                total_tokens=total_tokens
            )
            # Сообщение о начале сессии
            await callback.message.edit_text(
                SESSION_STARTED_TEXT.format(
                    resistance=resistance,
                    emotion=emotion,
                    selected_persona=persona_data['persona']['name'],
                )
            )
            # Стейт - в сессии
            await state.set_state(MainMenu.in_session)

        case "back_main":
            # Идем назад
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
        # Выбор
        await state.update_data(resistance=callback.data)
        await callback.message.edit_text(
            EMOTION_SELECT_TEXT,
            reply_markup=session_emotion_menu()
        )
        await state.set_state(MainMenu.session_emotion)
    elif callback.data == "back_main":
        # Назад
        await callback.message.edit_text(
            BACK_TO_MENU_TEXT,
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)


# --- Выбор эмоции ---
@router.callback_query(MainMenu.session_emotion)
async def session_emotion_handler(callback: types.CallbackQuery, state: FSMContext, session_manager: SessionManager):
    await callback.answer()
    if callback.data.startswith("emotion_"):
        # Выбор
        await state.update_data(emotion=callback.data)
        
        personas = await session_manager.get_all_personas()
        persona_names = list(personas.keys())

        await callback.message.edit_text(
            CHOOSE_PERSONE_FOR_SESSION_TEXT,
            reply_markup=persona_selection_menu(persona_names)
        )
        await state.set_state(MainMenu.session_persona)
    elif callback.data == "back_to_resistance":
        # Вернутся к выбору сопротивления
        await callback.message.edit_text(
            SESSION_RESISTANCE_SELECT,
            reply_markup=session_resistance_menu()
        )
        await state.set_state(MainMenu.session_resistance)

# --- Выбор персонажа ---
@router.callback_query(MainMenu.session_persona)
async def session_persona_handler(callback: types.CallbackQuery, state: FSMContext, session_manager: SessionManager):
    await callback.answer()

    if callback.data.startswith("persona_"):
        selected_persona = callback.data.replace("persona_", "")
        personas = await session_manager.get_all_personas()
        persona_data = personas.get(selected_persona)
        
        if not persona_data:
            await callback.message.edit_text("Персонаж не найден. Попробуйте снова.")
            return
            
        persona_info = persona_data['persona']
        
        # Format persona details
        details = [
            f"🧍 Персонаж: {persona_info.get('name', 'Неизвестно')}",
            f"👤 Возраст: {persona_info.get('age', 'Неизвестно')}",
            f"🚻 Пол: {persona_info.get('gender', 'Неизвестно')}",
            f"💼 Профессия: {persona_info.get('profession', 'Неизвестно')}",
            "",
            "📝 Дополнительно:",
            f"  - Семейное положение: {persona_info.get('marital_status', 'Неизвестно')}",
            f"  - Проживание: {persona_info.get('living_situation', 'Неизвестно')}",
            f"  - Образование: {persona_info.get('education', 'Неизвестно')}"
        ]
        
        await state.update_data(persona_name=selected_persona)
        await callback.message.edit_text(
            CONFIRM_SESSION_TEXT + "\n\n" + "\n".join(details),
            reply_markup=session_confirm_menu()
        )
        await state.set_state(MainMenu.session_confirm)

    elif callback.data == "back_to_emotion":
        await callback.message.edit_text(
            EMOTION_SELECT_TEXT,
            reply_markup=session_emotion_menu()
        )
        await state.set_state(MainMenu.session_emotion)