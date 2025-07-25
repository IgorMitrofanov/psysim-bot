from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states import MainMenu
from handlers.utils import calculate_typing_delay
from datetime import datetime
from typing import List
from core.persones.persona_decision_layer import PersonaDecisionLayer
from core.persones.persona_humanization_layer import PersonaHumanizationLayer
from core.persones.persona_instruction_layer import PersonaSalterLayer
from core.persones.persona_response_layer import PersonaResponseLayer
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from database.crud import get_user
import random
import asyncio
from services.session_manager import SessionManager
from config import logger
from collections import deque
import time

router = Router(name="session_interaction")

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
        
        db_user = await get_user(session, telegram_id=message.from_user.id)
        
        # Проверяем, активна ли ещё сессия
        if not await session_manager.is_session_active(db_user.id, session):
            await end_session_cleanup(message, state, session, session_manager)
            return
        
        # Если бот уже отвечает, добавляем сообщение в очередь
        if data.get("is_bot_responding", False):
            message_queue = data.get("message_queue", deque())
            if len(message_queue) >= 5:  # Лимит очереди
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
                await message.answer("<i>Персонаж предпочел не отвечать на это.</i>")
                responser.update_history("*молчание, ваш персонаж (пациент) предпочел не отвечать*", False)
                meta_history.append({"role": "Вы (пациент)", "content": "*молчание, ваш персонаж (пациент) предпочел не отвечать*"})
                if db_user:
                    async with session_lock(state):  # Захватываем блокировку для работы с историей
                        await session_manager.add_message_to_history(
                            db_user.id,
                            "Персонаж предпочел не отвечать на это.",
                            is_user=False,
                            tokens_used=tokens_used
                        )
            try:

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
    finally:
        await session.close()

        
async def check_inactivity(state: FSMContext, message: types.Message, delay: int, session: AsyncSession, session_manager: SessionManager):
    """Проверяет неактивность пользователя с учетом сообщений бота"""
    try:
        logger.info(f"Starting inactivity check (delay: {delay}s)")
        await asyncio.sleep(delay)
        
        async with session_lock(state):
            current_state = await state.get_state()
            if current_state != MainMenu.in_session:
                logger.info("Session already ended, skipping inactivity check")
                return
                
            data = await state.get_data()
            last_activity = data.get('last_activity', datetime.min)
            inactive_seconds = (datetime.now() - last_activity).total_seconds()
            
            logger.info(f"Current inactivity: {inactive_seconds:.1f}s")
            
            if inactive_seconds < delay:
                logger.info("Activity detected, cancelling inactivity check")
                return  # Была активность
                
            message_queue = data.get("message_queue", deque())
            
            if not message_queue:
                logger.info("No messages in queue, sending reminder")
                # тут тоже через ЛЛМ надо будет генерить реакцию
                phrases = [
                    "Я заметил паузу в нашем диалоге... вы всё ещё здесь?",
                    "Дайте знать, если хотите продолжить обсуждение",
                    "Я здесь, если у вас есть что добавить"
                ]
                await message.answer(random.choice(phrases))
                
                response_timer = asyncio.create_task(
                    wait_for_response(state, message, session, session_manager, 120) # Если пользователь после молчания в 120 сек, не проявил активности еще следующие 120 сек, то персонаж уходит и закрывает сессию.
                )
                await state.update_data(
                    response_timer=response_timer,
                    inactivity_check_time=datetime.now()
                )
                
    except asyncio.CancelledError:
        logger.info("Inactivity check cancelled")
    except Exception as e:
        logger.error(f"Inactivity check error: {e}")
    finally:
        await session.close()

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
    finally:
        await session.close()

# --- Очищение после сессии ---
async def end_session_cleanup(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    """Функция для корректного завершения сессии"""
    async with session_lock(state):
        try:
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
            await state.set_state(MainMenu.choosing)
        finally:
            await session.close()