from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states import MainMenu
from handlers.utils import calculate_typing_delay
from datetime import datetime
from typing import List, Optional
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
from uuid import uuid4

router = Router(name="session_interaction")

PROCESSING_DELAY = 6.5 # ожидание после последнего сообщения юзера, перед тем как персона начнет формировать ответ

INACTIVITY_DELAY = 120 # через сколько среагируем на молчание

# --- Логирование ---
def log_timer_operation(timer_name: str, operation: str, session_id: Optional[str] = None, user_id: Optional[int] = None):
    """Логирует операции с таймерами"""
    context = []
    if session_id:
        context.append(f"session_id={session_id}")
    if user_id:
        context.append(f"user_id={user_id}")
    context_str = " | ".join(context) if context else "no context"
    logger.debug(f"[TIMER {timer_name.upper()}] {operation.upper()} | {context_str}")

def log_session_operation(operation: str, session_id: Optional[str] = None, user_id: Optional[int] = None):
    """Логирует операции с сессией"""
    context = []
    if session_id:
        context.append(f"session_id={session_id}")
    if user_id:
        context.append(f"user_id={user_id}")
    context_str = " | ".join(context) if context else "no context"
    logger.info(f"[SESSION] {operation.upper()} | {context_str}")

# --- Блокировки и таймеры ---
@asynccontextmanager
async def session_lock(state: FSMContext):
    """Контекстный менеджер для безопасной работы с состоянием сессии"""
    lock_id = str(uuid4())[:8]
    data = await state.get_data()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    logger.debug(f"[LOCK {lock_id}] TRYING TO ACQUIRE | session_id={session_id} | user_id={user_id}")
    
    lock_timeout = 3  # Максимальное время ожидания блокировки
    start_time = time.time()
    
    while True:
        data = await state.get_data()
        if not data.get('session_locked'):
            break
        if time.time() - start_time > lock_timeout:
            logger.error(f"[LOCK {lock_id}] TIMEOUT EXCEEDED | session_id={session_id} | user_id={user_id}")
            break
        await asyncio.sleep(0.1)
    
    await state.update_data(session_locked=True)
    logger.debug(f"[LOCK {lock_id}] ACQUIRED | session_id={session_id} | user_id={user_id}")
    
    try:
        yield
    except Exception as e:
        logger.error(f"[LOCK {lock_id}] ERROR IN LOCKED SECTION: {e} | session_id={session_id} | user_id={user_id}")
        raise
    finally:
        await state.update_data(session_locked=False)
        logger.debug(f"[LOCK {lock_id}] RELEASED | session_id={session_id} | user_id={user_id}")


class SafeTimer:
    """Безопасный таймер с логированием и обработкой ошибок"""
    
    def __init__(self, name: str, state: FSMContext):
        self.name = name
        self.state = state
        self.task: Optional[asyncio.Task] = None
        self.cancelled = False
        self.completed = False
        self.session_id: Optional[str] = None
        self.user_id: Optional[int] = None
    
    async def initialize(self):
        """Инициализирует контекст таймера"""
        data = await self.state.get_data()
        self.session_id = data.get("session_id")
        self.user_id = data.get("user_id")
        log_timer_operation(self.name, "initialized", self.session_id, self.user_id)
    
    async def start(self, delay: float, callback, *args):
        """Запускает таймер"""
        await self.initialize()
        
        if self.task and not self.task.done():
            log_timer_operation(self.name, "already running - cancelling", self.session_id, self.user_id)
            await self.cancel()
        
        self.cancelled = False
        self.completed = False
        
        async def timer_task():
            try:
                log_timer_operation(self.name, f"started with delay {delay}s", self.session_id, self.user_id)
                await asyncio.sleep(delay)
                
                if self.cancelled:
                    log_timer_operation(self.name, "cancelled before execution", self.session_id, self.user_id)
                    return
                
                # Проверяем актуальность сессии перед выполнением
                current_data = await self.state.get_data()
                if current_data.get('session_id') != self.session_id:
                    log_timer_operation(self.name, "session changed - cancelling", self.session_id, self.user_id)
                    return
                
                log_timer_operation(self.name, "executing callback", self.session_id, self.user_id)
                await callback(*args)
                self.completed = True
                log_timer_operation(self.name, "completed successfully", self.session_id, self.user_id)
            except asyncio.CancelledError:
                log_timer_operation(self.name, "cancelled during execution", self.session_id, self.user_id)
                raise
            except Exception as e:
                logger.error(f"[TIMER {self.name.upper()}] ERROR IN CALLBACK: {e} | session_id={self.session_id} | user_id={self.user_id}")
                raise
        
        self.task = asyncio.create_task(timer_task())
        return self
    
    async def cancel(self):
        """Отменяет таймер"""
        if not self.task:
            return
            
        if self.task.done():
            log_timer_operation(self.name, "already completed - no need to cancel", self.session_id, self.user_id)
            return
            
        self.cancelled = True
        self.task.cancel()
        log_timer_operation(self.name, "cancellation requested", self.session_id, self.user_id)
        
        try:
            await self.task
            log_timer_operation(self.name, "cancellation confirmed", self.session_id, self.user_id)
        except asyncio.CancelledError:
            log_timer_operation(self.name, "was cancelled", self.session_id, self.user_id)
        except Exception as e:
            logger.error(f"[TIMER {self.name.upper()}] ERROR DURING CANCELLATION: {e} | session_id={self.session_id} | user_id={self.user_id}")

async def is_session_active(
    state: FSMContext,
    session_manager: Optional[SessionManager] = None,
    db_session: Optional[AsyncSession] = None
) -> bool:
    """
    Проверяет, активна ли сессия, учитывая:
    1. Состояние FSM
    2. Данные в состоянии
    3. Статус в SessionManager (если предоставлены)
    
    Args:
        state: Контекст состояния FSM
        session_manager: Опционально - менеджер сессий
        db_session: Опционально - сессия базы данных
        
    Returns:
        bool: True если сессия активна во всех источниках
    """
    # Проверяем состояние FSM и наличие session_id
    current_state = await state.get_state()
    data = await state.get_data()
    session_id = data.get('session_id')
    user_id = data.get('user_id')
    
    # Базовая проверка состояния FSM
    if current_state != MainMenu.in_session or not session_id:
        return False
    
    # Если не предоставлены session_manager или db_session, возвращаем результат по FSM
    if session_manager is None or db_session is None:
        return True
    
    try:
        # Проверяем статус сессии в менеджере
        is_active_in_manager = await session_manager.is_session_active(
            user_id=user_id,
            session_id=session_id,
            db_session=db_session
        )
        
        # Сессия активна только если активна и в FSM и в менеджере
        return is_active_in_manager
    except Exception as e:
        logger.error(f"Error checking session status in manager: {e} | session_id={session_id} | user_id={user_id}")
        # В случае ошибки считаем сессию неактивной для безопасности
        return False

async def clear_all_timers(state: FSMContext):
    """Отменяет все активные таймеры и очищает ссылки на них"""
    data = await state.get_data()
    cancelled = 0
    for timer_name in ['inactivity_timer', 'processing_timer']:
        timer = data.get(timer_name)
        if timer:
            try:
                await timer.cancel()
                cancelled += 1
            except Exception as e:
                logger.error(f"Error cancelling {timer_name}: {e}")
    await state.update_data({
        'inactivity_timer': None,
        'processing_timer': None,
    })
    logger.debug(f"Cancelled {cancelled} timers")


# --- Обработка сообщений во время сессии ---
@router.message(MainMenu.in_session)
async def session_interaction_handler(
    message: types.Message, 
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    # Получаем данные сессии для логирования
    data = await state.get_data()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    log_session_operation("message received", session_id, user_id)
    
    async with session_lock(state):
            
        db_user = await get_user(session, telegram_id=message.from_user.id)
        if not db_user:
            logger.error(f"User not found in database | telegram_id={message.from_user.id}")
            return
        
        # Если бот уже отвечает, добавляем сообщение в очередь
        if data.get("is_bot_responding", False):
            message_queue = data.get("message_queue", deque())
            if len(message_queue) >= 5:  # Лимит очереди
                logger.warning(f"Message queue limit exceeded | session_id={session_id} | user_id={user_id}")
                await asyncio.sleep(1.2)
                # TODO: генерация ЛЛМ
                await message.answer("Не могу так быстро! По медленее.")
                return
                
            message_queue.append(message.text)
            await state.update_data(
                message_queue=message_queue,
                last_activity=datetime.now()  # Обновляем активность при получении сообщения (чтобы бот не отвечал на 1 одно сообщение потом, если его перебили)
            )
            logger.debug(f"Message added to queue (queue size={len(message_queue)}) | session_id={session_id} | user_id={user_id}")
            return
        
        # Отменяем предыдущие таймеры
        for timer_name in ['inactivity_timer', 'processing_timer']:
            if timer := data.get(timer_name):
                logger.debug(f"Cancelling previous {timer_name} | session_id={session_id} | user_id={user_id}")
                await timer.cancel()
                
        # Проверяем, активна ли ещё сессия
        if not await session_manager.is_session_active(db_user.id, session):
            logger.warning(f"Session is no longer active | session_id={session_id} | user_id={user_id}")
            await end_session_cleanup(message, state, session, session_manager)
            return
        
        # Добавляем сообщение в очередь
        message_queue = data.get("message_queue", deque())
        message_queue.append(message.text)
        
        # Создаем новые таймеры
        inactivity_timer = SafeTimer("inactivity", state)
        processing_timer = SafeTimer("processing", state)
        
        # Обновляем состояние
        await state.update_data(
            message_queue=message_queue,
            is_bot_responding=True,
            last_activity=datetime.now(),
            inactivity_timer=inactivity_timer,
            processing_timer=processing_timer
        )
        
        # Запускаем таймеры
        await processing_timer.start(PROCESSING_DELAY, process_messages_after_delay, state, message, session, session_manager, PROCESSING_DELAY)
        await inactivity_timer.start(INACTIVITY_DELAY, check_inactivity, state, message, INACTIVITY_DELAY, session, session_manager)
        
        logger.debug(f"Timers started | session_id={session_id} | user_id={user_id}")

async def process_messages_after_delay(
    state: FSMContext,
    message: types.Message,
    session: AsyncSession,
    session_manager: SessionManager,
    delay: int
):
    """Обрабатывает все сообщения после задержки"""
    data = await state.get_data()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    logger.debug(f"Processing messages after delay {delay}s | session_id={session_id} | user_id={user_id}")
    
    try:
        async with session_lock(state):
            if not await session_manager.is_session_active(user_id, session):
                logger.debug(f"Session ended before inactivity check | session_id={session_id} | user_id={user_id}")
                return
            
            # Устанавливаем флаг ответа бота
            await state.update_data(is_bot_responding=True)
                
            data = await state.get_data()
            message_queue = data.get("message_queue", deque())
            
            if not message_queue:
                logger.debug(f"No messages in queue to process | session_id={session_id} | user_id={user_id}")
                await state.update_data(is_bot_responding=False)
                return
            
            # Берем ВСЕ сообщения из очереди и объединяем их (чтобы бот не отвечал на 1 одно сообщение потом, если его перебили)
            combined_messages = []
            while message_queue:
                combined_messages.append(message_queue.popleft())
            
            combined_message = "\n".join(combined_messages)
            message_queue.clear()
            await state.update_data(message_queue=message_queue)
        
            # Получаем необходимые данные из состояния
            meta_history: List = data.get("meta_history", [])
            decisioner: PersonaDecisionLayer = data.get("decisioner")
            salter: PersonaSalterLayer = data.get("salter")
            responser: PersonaResponseLayer = data.get("responser")
            humanizator: PersonaHumanizationLayer = data.get("humanizator")
            total_tokens = data.get("total_tokens", 0)
            
            # Логируем пользовательские сообщения
            db_user = await get_user(session, telegram_id=message.from_user.id)
            if db_user:
                logger.debug(f"Adding user message to history | session_id={session_id} | user_id={user_id}")
                await session_manager.add_message_to_history(
                    db_user.id,
                    combined_message,
                    is_user=True,
                    tokens_used=0 # Никаких токенов не задействовано
                )
            
            meta_history.append({"role": "Психотерапевт (ваш собеседник)", "content": combined_message})
            
            # Обработка сообщения через все слои ИИ
            logger.debug(f"Making decision for message | session_id={session_id} | user_id={user_id}")
            
            # Принятие решение
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
                    logger.debug(f"Typing indicator started | session_id={session_id} | user_id={user_id}")
                    
                    # Подсолка сообщения
                    logger.debug(f"Salting message | session_id={session_id} | user_id={user_id}")
                    salted_msg, tokens_used = await salter.salt_message(combined_message, decision, recent_decisions, meta_history)
                    total_tokens += tokens_used
                    
                    # Генерация ответа
                    responser.update_history(salted_msg)
                    logger.debug(f"Generating response | session_id={session_id} | user_id={user_id}")
                    response, tokens_used = await responser.get_response()
                    total_tokens += tokens_used
                    
                    # Хуманизация ответа
                    logger.debug(f"Humanizing response | session_id={session_id} | user_id={user_id}")
                    refined_response, tokens_used = await humanizator.humanization_respond(
                        raw_response=response,
                        history=meta_history
                    )
                    total_tokens += tokens_used
                    
                    refined_response = refined_response.replace("`", "").replace("-", "").replace("'", "")
                    
                    logger.info(f"Final LLM response (with humanization): {refined_response} | session_id={session_id} | user_id={user_id}")
                    
                    # Разделение ответа на части
                    response_parts = [part.strip() for part in refined_response.split("||") if part.strip()] if "||" in refined_response else [refined_response]
                    
                    # Обновление истории
                    responser.update_history(" ".join(response_parts), False)
                    meta_history.append({"role": "Вы (пациент)", "content": " ".join(response_parts)})
                    
                    # Отправка ответа
                    logger.debug(f"Sending response parts (count={len(response_parts)}) | session_id={session_id} | user_id={user_id}")
                    for part in response_parts:
                        delay = calculate_typing_delay(part)
                        try:
                            await asyncio.sleep(delay)
                            await message.answer(part)
                        except asyncio.CancelledError:
                            continue
                        
                    # Проверяем, есть ли новые сообщения в очереди (чтобы бот не отвечал на 1 одно сообщение потом, если его перебили)
                    data = await state.get_data()
                    current_queue = data.get("message_queue", deque())
                    if current_queue:
                        logger.debug(f"New messages arrived during response (count={len(current_queue)}), processing them | session_id={session_id} | user_id={user_id}")
                        # Не очищаем очередь - она будет обработана в следующей итерации
                        await process_messages_after_delay(state, message, session, session_manager, 0)
                    else:
                        await state.update_data(is_bot_responding=False)
                    
                    # Логирование ответа
                    if db_user:
                        logger.debug(f"Adding bot response to history | session_id={session_id} | user_id={user_id}")
                        await session_manager.add_message_to_history(
                            db_user.id,
                            " ".join(response_parts),
                            is_user=False,
                            tokens_used=total_tokens
                        )
                    
                    if decision == "disengage":
                        logger.debug(f"Persona decided to disengage | session_id={session_id} | user_id={user_id}")
                        await asyncio.sleep(1)
                        await message.answer("<i>Персонаж решил уйти...</i>")
                        await asyncio.sleep(1)
                        await end_session_cleanup(message, state, session, session_manager)
                finally:
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass
                    logger.debug(f"Typing indicator stopped | session_id={session_id} | user_id={user_id}")

                    await state.update_data(is_bot_responding=False)
                    
                    # Проверяем, есть ли новые сообщения в очереди
                    data = await state.get_data()
                    if data.get("message_queue", deque()):
                        logger.debug(f"Processing remaining messages in queue | session_id={session_id} | user_id={user_id}")
                        await process_messages_after_delay(state, message, session, session_manager, 0)
            else:
                logger.debug(f"Persona chose silence | session_id={session_id} | user_id={user_id}")
                await message.answer("<i>Персонаж предпочел не отвечать на это.</i>")
                responser.update_history("*молчание, ваш персонаж (пациент) предпочел не отвечать*", False)
                meta_history.append({"role": "Вы (пациент)", "content": "*молчание, ваш персонаж (пациент) предпочел не отвечать*"})
                if db_user:
                    async with session_lock(state):
                        logger.debug(f"Adding silence to history | session_id={session_id} | user_id={user_id}")
                        await session_manager.add_message_to_history(
                            db_user.id,
                            "Персонаж предпочел не отвечать на это.",
                            is_user=False,
                            tokens_used=total_tokens
                        )

            # Обновляем состояние и перезапускаем таймеры
            async with session_lock(state):
                await state.update_data(
                    is_bot_responding=False,
                    last_activity=datetime.now(),
                    meta_history=meta_history,
                    total_tokens=total_tokens
                )
                
                # Перезапускаем таймер неактивности
                data = await state.get_data()
                if inactivity_timer := data.get('inactivity_timer'):
                    logger.debug(f"Restarting inactivity timer | session_id={session_id} | user_id={user_id}")
                    await inactivity_timer.cancel()
                    inactivity_timer = SafeTimer("inactivity", state)
                    await inactivity_timer.start(120, check_inactivity, state, message, 120, session, session_manager)
                    await state.update_data(inactivity_timer=inactivity_timer)

    except Exception as e:
        logger.error(f"Error processing messages: {e} | session_id={session_id} | user_id={user_id}")
        await state.update_data(is_bot_responding=False)
    finally:
        # Проверяем, нужно ли завершить сессию после ответа
        data = await state.get_data()
        if data.get("should_end_session_after_response", False):
            await end_session_cleanup(message, state, session, session_manager)
        await session.close()

async def check_inactivity(
    state: FSMContext,
    message: types.Message,
    delay: int,
    session: AsyncSession,
    session_manager: SessionManager
):
    """Проверяет неактивность пользователя с учетом сообщений бота"""
    data = await state.get_data()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    logger.debug(f"Starting inactivity check (delay={delay}s) | session_id={session_id} | user_id={user_id}")
    
    try:
        async with session_lock(state):
            # Проверяем, активна ли ещё сессия
            if not await session_manager.is_session_active(user_id, session):
                logger.debug(f"Session ended before inactivity check | session_id={session_id} | user_id={user_id}")
                return
                
            data = await state.get_data()
            # Если бот отвечает, откладываем проверку неактивности
            if data.get('is_bot_responding', False):
                logger.debug(f"Bot is responding - postponing inactivity check | session_id={session_id} | user_id={user_id}")
                return
            
            last_activity = data.get('last_activity', datetime.min)
            inactive_seconds = (datetime.now() - last_activity).total_seconds()
            
            logger.debug(f"Current inactivity: {inactive_seconds:.1f}s | session_id={session_id} | user_id={user_id}")
            
            if inactive_seconds < delay:
                logger.debug(f"Activity detected, cancelling inactivity check | session_id={session_id} | user_id={user_id}")
                return  # Была активность
                
            message_queue = data.get("message_queue", deque())
            
            if not message_queue:
                logger.debug(f"No messages in queue, adding silence message | session_id={session_id} | user_id={user_id}")
                
                # Добавляем специальное сообщение о молчании в очередь
                silence_message = f"*молчание в течение {INACTIVITY_DELAY} секунд...*"
                message_queue.append(silence_message)
                
                # Обновляем состояние с новой очередью и флагом ответа бота
                await state.update_data(
                    message_queue=message_queue,
                    is_bot_responding=True,
                    last_activity=datetime.now()  # Обновляем активность
                )
                
                 # Логируем пользовательские сообщения
                db_user = await get_user(session, telegram_id=message.from_user.id)
                if db_user:
                    logger.debug(f"Adding user message to history | session_id={session_id} | user_id={user_id}")
                    await session_manager.add_message_to_history(
                        db_user.id,
                        silence_message,
                        is_user=True,
                        tokens_used=0 # Логгированием сообщение пользователя о молчании
                    )
                
                # Запускаем обработку сообщения о молчании
                await process_messages_after_delay(
                    state, 
                    message, 
                    session, 
                    session_manager, 
                    0  # Немедленная обработка
                )
                
    except asyncio.CancelledError:
        logger.debug(f"Inactivity check cancelled | session_id={session_id} | user_id={user_id}")
    except Exception as e:
        logger.error(f"Inactivity check error: {e} | session_id={session_id} | user_id={user_id}")
                
    except asyncio.CancelledError:
        logger.debug(f"Response wait cancelled | session_id={session_id} | user_id={user_id}")
    except Exception as e:
        logger.error(f"Wait for response error: {e} | session_id={session_id} | user_id={user_id}")
    finally:
        await session.close()

# --- Очищение после сессии ---
async def end_session_cleanup(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    """Функция для корректного завершения сессии с гарантированным сбросом таймеров"""
    data = await state.get_data()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    log_session_operation("starting cleanup", session_id, user_id)
    
    async with session_lock(state):
        try:
            # Ждем завершения ответа бота, если он в процессе
            while data.get("is_bot_responding", False):
                logger.debug(f"Waiting for bot to finish responding | session_id={session_id} | user_id={user_id}")
                await asyncio.sleep(5)
                data = await state.get_data()

            # Отменяем все таймеры и очищаем их из состояния
            timer_names = ['inactivity_timer', 'processing_timer']
            cancelled_timers = 0
            
            for timer_name in timer_names:
                if timer := data.get(timer_name):
                    logger.debug(f"Cancelling {timer_name} | session_id={session_id} | user_id={user_id}")
                    try:
                        if not timer.completed and not timer.cancelled:
                            await timer.cancel()
                            cancelled_timers += 1
                    except Exception as e:
                        logger.error(f"Error cancelling {timer_name}: {e} | session_id={session_id} | user_id={user_id}")

            # Очищаем ссылки на таймеры в состоянии
            await state.update_data({
                'inactivity_timer': None,
                'processing_timer': None,
                'message_queue': deque(),
                'is_bot_responding': False
            })
            
            logger.debug(f"Cancelled {cancelled_timers}/{len(timer_names)} timers | session_id={session_id} | user_id={user_id}")
            
            # Завершаем сессию
            db_user = await get_user(session, telegram_id=message.from_user.id)
            if session_id and db_user:
                logger.debug(f"Ending session in manager | session_id={session_id} | user_id={user_id}")
                try:
                    await session_manager.end_session(
                        user_id=db_user.id,
                        db_session=session,
                        session_id=session_id
                    )
                    log_session_operation("session ended in manager", session_id, user_id)
                except Exception as e:
                    logger.error(f"Error ending session in manager: {e} | session_id={session_id} | user_id={user_id}")
            
            # Очищаем состояние
            logger.debug(f"Clearing state | session_id={session_id} | user_id={user_id}")
            await state.clear()
            await state.set_state(MainMenu.choosing)
            
            log_session_operation("cleanup completed", session_id, user_id)
        except Exception as e:
            logger.error(f"Error during session cleanup: {e} | session_id={session_id} | user_id={user_id}")
            raise
        # finally:
        #     await session.close()