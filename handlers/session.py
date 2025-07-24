from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states import MainMenu
from keyboards.builder import (
    session_resistance_menu,
    session_emotion_menu,
    session_format_menu,
    session_confirm_menu,
    main_menu,
    persona_selection_menu,
    subscription_keyboard_when_sessions_left
)
from core.persones.prompt_builder import build_prompt, build_humalizate_prompt
from core.persones.llm_engine import get_response
from handlers.utils import calculate_typing_delay
from datetime import datetime, timedelta
from config import config
from typing import List
from core.persones.persona_decision_layer import PersonaDecisionLayer
from core.persones.persona_humanization_layer import PersonaHumanizationLayer
from core.persones.persona_instruction_layer import PersonaSalterLayer
from core.persones.persona_response_layer import PersonaResponseLayer
from core.persones.persona_loader import load_personas
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user, save_session
from texts.session_texts import (
    SESSION_RESISTANCE_SELECT,
    EMOTION_SELECT_TEXT,
    FORMAT_SELECT_TEXT,
    CONFIRM_SESSION_TEXT,
    SESSION_STARTED_TEXT,
    NO_USER_TEXT,
    SESSION_RESET_TEXT,
    SESSION_RESET_ERROR_TEXT,
    PERSONA_NOT_FOUND_TEXT,
    SESSION_END_TEXT,
    NO_QUOTA_OR_BONUS_FOR_SESSION,
    CHOOSE_PERSONE_FOR_SESSION_TEXT,
    res_map,
    emo_map,
    format_map
)
import random
import asyncio
from texts.common import BACK_TO_MENU_TEXT
from aiogram.types import Message
from services.session_manager import SessionManager
from aiogram.filters import Command
from config import logger

router = Router(name="session")

# ВАЖНО: Здесь используется абстрактный менеджер работы с сессиями, он работает с user_id [int] - это айди из БД, не телеграм айди!
# Менеджер сам найдет телеграм айди юзера с помощью метода из crud

# --- Команда ресета - вынужденной остановки сессии, она в БД не записывается ---
@router.message(Command("reset_session"))
async def reset_session_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    
    # TODO: Даже после ресета, если сообщения персоне были отправлены - она ответит потом юзеру. надо это исправить как то
    data = await state.get_data()
    session_id = data.get("session_id")

    if session_id:
        await session_manager.abort_session(message.from_user.id, session, session_id=session_id)
        # к аборту сессии надо будет убрать стиране данных сессии - иначе их бесконечно абузить можно
        await message.answer(SESSION_RESET_TEXT)
    else:
        await message.answer(SESSION_RESET_ERROR_TEXT)

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
    # Для индикатора "печатает"
    async def typing_callback():
        while True:
            await message.bot.send_chat_action(message.chat.id, 'typing')
            await asyncio.sleep(4)

    data = await state.get_data()
    # История сообщений для мета ИИ (без подсказок с промежуточных слоев)
    meta_history: List = data.get("meta_history")

    # Загрузим настроеные слои ИИ "персоны" под конкретную сессию
    decisioner: PersonaDecisionLayer = data.get("decisioner")
    salter: PersonaSalterLayer = data.get("salter")
    responser: PersonaResponseLayer = data.get("responser")
    humanizator: PersonaHumanizationLayer = data.get("humanizator")

    # Общий подсчет токенов
    total_tokens = data.get("total_tokens")

    # Получаем юзера из БД
    db_user = await get_user(session, telegram_id=message.from_user.id)

    # Проверяем, активна ли ещё сессия
    if not await session_manager.is_session_active(db_user.id, session):
        await message.answer(SESSION_END_TEXT)
        await message.answer(BACK_TO_MENU_TEXT, reply_markup=main_menu())
        await state.clear()
        await state.set_state(MainMenu.choosing)
        return

    # Логируем пользовательское сообщение в менеджер сессий (для записи в БД)
    await session_manager.add_message_to_history(
        db_user.id,
        message.text,
        is_user=True,
        tokens_used=len(message.text) // 4
    )

    # Помещаем сообщение пользователя в мета-историю
    meta_history.append({"role": "Психотерапевт (ваш собеседник)", "content": message.text})

    # Сначала 1 слой ИИ принимает решение (всегда на основе мета истории, вообще все ИИ кроме основной работают с мета-историей):

    decision, tokens_used = await decisioner.make_decision(message.text, meta_history)

    # Получаем общую хрологию решений для мета-ИИ
    recent_decisions = decisioner.get_recent_decisions()

    if decision != "silence":
        try:
            # Если решение не молчать
            # Включаем индикатор печатает, т.к. персона точно ответит
            typing_task = asyncio.create_task(typing_callback())
            # Надо "подсолить" сообщение юзера для основной ИИ с помощью 2 слоя нейросети
            salted_msg, tokens_used = await salter.salt_message(message.text, decision, recent_decisions, meta_history)
            total_tokens += tokens_used
            # Теперь у нас есть "соленое" сообщение юзера для основной нейросети (3 слой)
            # Добавляем "соленое" сообщение в историю основной нейросети
            responser.update_history(salted_msg)
            # Генерируем ответ у основной нейросети (3 слой)
            response, tokens_used = await responser.get_response()
            total_tokens += tokens_used
            # Хуманизация другой ИИ (4 слой)
            refined_response, tokens_used = await humanizator.humanization_respond(
                raw_response=response,
                history=meta_history
            )

            # Удалим мусор, приходится жертвовать тире и ковычками такими, т.к. бывает модели высерают
            refined_response = refined_response.replace("`", "")
            refined_response = refined_response.replace("-", "")
            refined_response = refined_response.replace("'", "")

            total_tokens += tokens_used

            logger.info(f"Final LLM response (with humanization): {refined_response}")
            # Разделение ответа на части по ||
            if "||" in refined_response:
                response_parts = [part.strip() for part in refined_response.split("||") if part.strip()]
                logger.info(f"Split response into parts: {response_parts}")
            else:
                response_parts = [refined_response]
            
            # Обновление истории (сохраняем как единое сообщение)
            responser.update_history(" ".join(response_parts), False)
            meta_history.append({"role": "Вы (пациент)", "content": " ".join(response_parts)})
            if isinstance(response_parts, list):
                for part in response_parts:
                    clean_part = part.replace('"', '')
                    delay = calculate_typing_delay(clean_part)
                    await asyncio.sleep(delay)
                    await message.answer(clean_part)
                typing_task.cancel()
        finally:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass
                else:
                    await message.answer("<code>Персонаж не смог ответить на сообщение.</code>")
        if decision == "disengage":
            # если решение было уйти - завершаем сессию
            await message.answer("<i>Персонаж решил уйти...</i>")
            await session_manager.add_message_to_history(db_user.id, response_parts, is_user=False, tokens_used=total_tokens)
            session_id = data.get("session_id")
            if session_id:
                await session_manager.end_session(user_id=db_user.id, db_session=session, session_id=session_id)
                await state.clear()
                await state.set_state(MainMenu.choosing)
    else:
        # просто молчим
        await message.answer("<code>Персонаж предпочел не отвечать на это.</code>")
        # Добавляем в БД что персона молчит
        await session_manager.add_message_to_history(db_user.id, "[silence]", is_user=False, tokens_used=tokens_used)
        # Обновляем историю для основной нейросети и мета-историю
        responser.update_history("*молчание, ваш персонаж (пациент) предпочел не отвечать*", False)
        meta_history.append({"role": "Вы (пациент)", "content": "*молчание, ваш персонаж (пациент) предпочел не отвечать*"})

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
            personas = load_personas()
            persona_data = personas.get(persona_name)
            if not persona_data:
                await callback.message.edit_text("Персонаж не найден. Попробуйте снова.")
                await state.set_state(MainMenu.session_format)
                return
            
            resistance_raw = data.get("resistance")
            emotion_raw = data.get("emotion")
            format_raw = data.get("format")
            
            resistance =res_map.get(resistance_raw)
            emotion = emo_map.get(emotion_raw)
            format = format_map.get(format_raw)
            
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
                    reply_markup=subscription_keyboard_when_sessions_left()
                )
                return
            
            # Делегируем менеджеру сессий начать сессию, и запрашиваем у него ее айди
            session_id = await session_manager.start_session(
                db_session=session,
                user_id=db_user.id,
                is_free=is_free,
                persona_name=persona_name,
                resistance=emotion,
                emotion=resistance
            )
            # Обновляем данные в стейт
            await state.update_data(
                session_start=datetime.utcnow().isoformat(),
                session_id=session_id,
                resistance=resistance,
                emotion=emotion,
                format=format,
                decisioner=decisioner,
                responser=responser,
                meta_history=meta_history,
                salter=salter,
                humanizator=humanizator,
                total_tokens=total_tokens
            )
            # Сообщение о начале сессии
            await callback.message.edit_text(
                SESSION_STARTED_TEXT.format(
                    resistance=resistance,
                    emotion=emotion,
                    selected_persona=persona_data['persona']['name'],
                    format=format
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
async def session_emotion_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data.startswith("emotion_"):
        # Выбор
        await state.update_data(emotion=callback.data)
        await callback.message.edit_text(
            FORMAT_SELECT_TEXT,
            reply_markup=session_format_menu()
        )
        await state.set_state(MainMenu.session_format)
    elif callback.data == "back_to_resistance":
        # Вернутся к выбору сопротивления
        await callback.message.edit_text(
            SESSION_RESISTANCE_SELECT,
            reply_markup=session_resistance_menu()
        )
        await state.set_state(MainMenu.session_resistance)

# --- Выбор формата --- 
# На самом деле думаю убрать это. Просто если риходит голосовая от пользователя - если тариф 
# позволяет - обрабатываем, если нет, предалагем перейти на тариф где есть гс
@router.callback_query(MainMenu.session_format)
async def session_format_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["format_text", "format_audio"]:
        await state.update_data(format=callback.data)

        personas = load_personas()
        persona_names = list(personas.keys())

        await callback.message.edit_text(
            CHOOSE_PERSONE_FOR_SESSION_TEXT,
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