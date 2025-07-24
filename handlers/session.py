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
from contextlib import asynccontextmanager
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
from collections import deque
import time
router = Router(name="session")

# ВАЖНО: Здесь используется абстрактный менеджер работы с сессиями, он работает с user_id [int] - это айди из БД, не телеграм айди!
# Менеджер сам найдет телеграм айди юзера с помощью метода из crud

# --- Блокировки и таймеры ---
@asynccontextmanager
async def session_lock(state: FSMContext):
    """Контекстный менеджер для безопасной работы с состоянием сессии"""
    lock_timeout = 3  # Максимальное время ожидания блокировки
    start_time = time.time()
    
    while True:
        data = await state.get_data()
        if not data.get('session_locked'):
            break
        if time.time() - start_time > lock_timeout:
            logger.error("Session lock timeout exceeded!")
            break
        await asyncio.sleep(0.1)
    
    await state.update_data(session_locked=True)
    try:
        yield
    finally:
        await state.update_data(session_locked=False)

async def safe_timer(state: FSMContext, duration: int, callback, *args):
    """Таймер с проверкой блокировки и состояния сессии"""
    try:
        await asyncio.sleep(duration)
        
        async with session_lock(state):
            current_state = await state.get_state()
            if current_state == MainMenu.in_session:
                await callback(*args)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Timer error: {e}")

# --- Команда ресета - вынужденной остановки сессии, она в БД не записывается ---
@router.message(Command("reset_session"))
async def reset_session_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    async with session_lock(state):
        data = await state.get_data()
        session_id = data.get("session_id")

        if session_id:
            await end_session_cleanup(message, state, session, session_manager)
            await message.answer(SESSION_RESET_TEXT)
        else:
            await message.answer(SESSION_RESET_ERROR_TEXT)

from collections import deque


# --- Обработка сообщений во время сессии ---
@router.message(MainMenu.in_session)
async def session_interaction_handler(
    message: types.Message, 
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    async with session_lock(state):
        current_state = await state.get_state()
        if current_state != MainMenu.in_session:
            await message.answer("⚠️ Сессия уже завершена. Начните новую, если хотите продолжить.")
            return
            
        data = await state.get_data()
        
        # Если бот уже отвечает, добавляем сообщение в очередь
        if data.get("is_bot_responding", False):
            message_queue = data.get("message_queue", deque())
            if len(message_queue) >= 3:  # Лимит очереди
                await asyncio.sleep(1.2)
                await message.answer("Не могу так быстро! По медленее.")
                return
                
            message_queue.append(message.text)
            await state.update_data(message_queue=message_queue)
            return
        
        # Отменяем предыдущие таймеры
        for timer in ['inactivity_timer', 'processing_timer']:
            if timer in data:
                data[timer].cancel()
        
        # Добавляем сообщение в очередь
        message_queue = data.get("message_queue", deque())
        message_queue.append(message.text)
        
        # Обновляем состояние
        await state.update_data(
            message_queue=message_queue,
            is_bot_responding=True,
            last_activity=datetime.now()
        )
        
        # Запускаем новые таймеры с защитой
        processing_timer = asyncio.create_task(
            safe_timer(state, 10, process_messages_after_delay, state, message, session, session_manager, 10)
        )
        inactivity_timer = asyncio.create_task(
            safe_timer(state, 120, check_inactivity, state, message, 120, session, session_manager)
        )
                
        await state.update_data(
            processing_timer=processing_timer,
            inactivity_timer=inactivity_timer
        )

async def process_messages_after_delay(
    state: FSMContext,
    message: types.Message,
    session: AsyncSession,
    session_manager: SessionManager,
    delay: int
):
    """Обрабатывает все сообщения после задержки"""
    try:
        async with session_lock(state):
            current_state = await state.get_state()
            if current_state != MainMenu.in_session:
                return
                
            data = await state.get_data()
            message_queue = data.get("message_queue", deque())
            
            if not message_queue:
                return
                
            # Обработка сообщения (ваш существующий код)
            combined_message = "\n".join(message_queue)
            message_queue.clear()
            await state.update_data(message_queue=message_queue)
        
            # Получаем необходимые данные из состояния
            meta_history: List = data.get("meta_history", [])
            decisioner: PersonaDecisionLayer = data.get("decisioner")
            salter: PersonaSalterLayer = data.get("salter")
            responser: PersonaResponseLayer = data.get("responser")
            humanizator: PersonaHumanizationLayer = data.get("humanizator")
            total_tokens = data.get("total_tokens", 0)
            
            # Логируем пользовательские сообщения в менеджер сессий
            db_user = await get_user(session, telegram_id=message.from_user.id)
            if db_user:
                await session_manager.add_message_to_history(
                    db_user.id,
                    combined_message,
                    is_user=True,
                    tokens_used=len(combined_message) // 4
                )
            
            # Помещаем сообщение пользователя в мета-историю
            meta_history.append({"role": "Психотерапевт (ваш собеседник)", "content": combined_message})
            
            # Обработка сообщения через все слои ИИ
            decision, tokens_used = await decisioner.make_decision(combined_message, meta_history)
            total_tokens += tokens_used
            
            recent_decisions = decisioner.get_recent_decisions()
            
            if decision != "silence":
                try:
                    # Индикатор печатает
                    async def typing_callback():
                        while True:
                            await message.bot.send_chat_action(message.chat.id, 'typing')
                            await asyncio.sleep(4)
                    
                    typing_task = asyncio.create_task(typing_callback())
                    
                    # Подсолка сообщения
                    salted_msg, tokens_used = await salter.salt_message(combined_message, decision, recent_decisions, meta_history)
                    total_tokens += tokens_used
                    
                    # Генерация ответа
                    responser.update_history(salted_msg)
                    response, tokens_used = await responser.get_response()
                    total_tokens += tokens_used
                    
                    # Хуманизация ответа
                    refined_response, tokens_used = await humanizator.humanization_respond(
                        raw_response=response,
                        history=meta_history
                    )
                    total_tokens += tokens_used
                    
                    # Очистка ответа
                    refined_response = refined_response.replace("`", "").replace("-", "").replace("'", "")
                    
                    logger.info(f"Final LLM response (with humanization): {refined_response}")
                    
                    # Разделение ответа на части
                    response_parts = [part.strip() for part in refined_response.split("||") if part.strip()] if "||" in refined_response else [refined_response]
                    
                    # Обновление истории
                    responser.update_history(" ".join(response_parts), False)
                    meta_history.append({"role": "Вы (пациент)", "content": " ".join(response_parts)})
                    
                    # Отправка ответа с защитой от прерывания
                    for part in response_parts:
                        # clean_part = part.replace('"', '')
                        delay = calculate_typing_delay(part)
                        try:
                            await asyncio.sleep(delay)
                            await message.answer(part)
                        except asyncio.CancelledError:
                            # Если отправка была прервана, завершаем оставшиеся части
                            continue
                    
                    # Логирование ответа
                    if db_user:
                        await session_manager.add_message_to_history(
                            db_user.id,
                            " ".join(response_parts),
                            is_user=False,
                            tokens_used=total_tokens
                        )
                    
                    if decision == "disengage":
                        await asyncio.sleep(1)
                        await message.answer("<i>Персонаж решил уйти...</i>")
                        await asyncio.sleep(1)
                        # Завершаем сессию
                        await end_session_cleanup(message, state, session, session_manager)
                finally:
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass

                    # Помечаем, что бот закончил отвечать
                    await state.update_data(is_bot_responding=False)
                    
                    # Проверяем, есть ли новые сообщения в очереди
                    data = await state.get_data()
                    if data.get("message_queue", deque()):
                        # Если есть, обрабатываем их
                        await process_messages_after_delay(state, message, session, session_manager, 0)
            else:
                await message.answer("<code>Персонаж предпочел не отвечать на это.</code>")
            try:
                if db_user:
                    async with session_lock(state):  # Захватываем блокировку для работы с историей
                        await session_manager.add_message_to_history(
                            db_user.id,
                            "[silence]",
                            is_user=False,
                            tokens_used=tokens_used
                        )
                        
                # Обновляем историю без блокировки, так как это локальные объекты
                responser.update_history("*молчание, ваш персонаж (пациент) предпочел не отвечать*", False)
                meta_history.append({"role": "Вы (пациент)", "content": "*молчание, ваш персонаж (пациент) предпочел не отвечать*"})

                # Важно: сбрасываем флаг ответа и перезапускаем таймеры
                async with session_lock(state):
                    await state.update_data(
                        is_bot_responding=False,
                        last_activity=datetime.now()  # Обновляем время активности
                    )
                    
                    # Перезапускаем таймер неактивности
                    data = await state.get_data()
                    if 'inactivity_timer' in data:
                        data['inactivity_timer'].cancel()
                        
                    inactivity_timer = asyncio.create_task(
                        safe_timer(state, 120, check_inactivity, state, message, 120, session, session_manager)
                    )
                    await state.update_data(inactivity_timer=inactivity_timer)

            except Exception as e:
                logger.error(f"Error in silence handling: {e}")
                async with session_lock(state):
                    await state.update_data(is_bot_responding=False)
                
            await state.update_data(
                meta_history=meta_history,
                total_tokens=total_tokens
            )
    except Exception as e:
        logger.error(f"Error processing messages: {e}")
        await state.update_data(is_bot_responding=False)

async def check_inactivity(state: FSMContext, message: types.Message, delay: int, session: AsyncSession, session_manager: SessionManager):
    """Проверяет неактивность пользователя с учетом сообщений бота"""
    try:
        await asyncio.sleep(delay)
        
        async with session_lock(state):
            current_state = await state.get_state()
            if current_state != MainMenu.in_session:
                return
                
            data = await state.get_data()
            last_activity = data.get('last_activity', datetime.min)
            
            if (datetime.now() - last_activity).total_seconds() < delay:
                return  # Была активность
                
            message_queue = data.get("message_queue", deque())
            
            if not message_queue:
                phrases = [
                    "Я заметил паузу в нашем диалоге... вы всё ещё здесь?",
                    "Дайте знать, если хотите продолжить обсуждение",
                    "Я здесь, если у вас есть что добавить"
                ]
                # тут тоже через ЛЛМ надо будет генерить реакцию
                await message.answer(random.choice(phrases))
                
                response_timer = asyncio.create_task(
                    wait_for_response(state, message, session, session_manager, 30)
                )
                await state.update_data(
                    response_timer=response_timer,
                    inactivity_check_time=datetime.now()
                )
                
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Inactivity check error: {e}")

async def wait_for_response(
    state: FSMContext,
    message: types.Message,
    session: AsyncSession,
    session_manager: SessionManager,
    delay: int
):
    """Ожидает ответа после проверки активности"""
    try:
        await asyncio.sleep(delay)
        
        async with session_lock(state):
            current_state = await state.get_state()
            if current_state != MainMenu.in_session:
                return
                
            data = await state.get_data()
            last_activity = data.get('last_activity', datetime.min)
            last_check = data.get('inactivity_check_time', datetime.min)
            
            if last_activity > last_check:
                return  # Была активность
                
            message_queue = data.get("message_queue", deque())
            if not message_queue:
                await message.answer("<i>Персонаж ушел..</i>")
                await end_session_cleanup(message, state, session, session_manager)
                
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Wait for response error: {e}")

# --- Очищение после сессии ---
async def end_session_cleanup(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    """Функция для корректного завершения сессии"""
    async with session_lock(state):
        data = await state.get_data()
        
        # Отменяем все таймеры
        timers = ['inactivity_timer', 'processing_timer', 'response_timer']
        for timer_name in timers:
            if timer := data.get(timer_name):
                if not timer.done():
                    timer.cancel()
                    try:
                        await timer
                    except:
                        pass
        
        # Завершаем сессию
        session_id = data.get("session_id")
        db_user = await get_user(session, telegram_id=message.from_user.id)
        if session_id and db_user:
            await session_manager.end_session(
                user_id=db_user.id,
                db_session=session,
                session_id=session_id
            )
        
        # Очищаем состояние
        await state.clear()
        await message.answer(SESSION_END_TEXT)
        await message.answer(BACK_TO_MENU_TEXT, reply_markup=main_menu())
        await state.set_state(MainMenu.choosing)

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