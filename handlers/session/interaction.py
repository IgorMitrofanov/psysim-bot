from aiogram import Bot, Router, types
from aiogram.fsm.context import FSMContext
from states import MainMenu
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user
import asyncio
from services.session_manager import SessionManager
from services.timer_manager import TimerManager, SafeTimer
from collections import deque

# utils session module
from .utils import session_lock
from .utils import end_session_cleanup
from .utils import process_messages_after_delay, check_inactivity
from .utils import PROCESSING_DELAY, INACTIVITY_DELAY

from config import logger

router = Router(name="session_interaction")


@router.message(MainMenu.in_session)
async def session_interaction_handler(
    message: types.Message, 
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager,
    bot: Bot,
    timer_manager: TimerManager
):
    """
    Обрабатывает сообщения пользователя в активной сессии.
    """
    # Получаем данные сессии для логирования
    data = await state.get_data()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    logger.debug(f"[SESSION INTERATION] Received message in session | session_id={session_id} | user_id={user_id}")
    
    async with session_lock(state):
            
        db_user = await get_user(session, telegram_id=message.from_user.id)
        if not db_user:
            logger.error(f"User not found in database | telegram_id={message.from_user.id}")
            return
        
        # Если бот уже отвечает, добавляем сообщение в очередь
        if data.get("is_bot_responding", False):
            message_queue = data.get("message_queue", deque())
            if len(message_queue) >= 5:  # Лимит очереди
                logger.warning(f"[SESSION INTERATION] Message queue limit exceeded | session_id={session_id} | user_id={user_id}")
                await asyncio.sleep(1.2)
                # TODO: генерация ЛЛМ
                await message.answer("не так много сообщений пожалуйста!!")
                return
                
            message_queue.append(message.text)
            
            await state.update_data(
                message_queue=list(message_queue), # реддис не переваривает очереди - нельзя сеарилизовать
                last_activity=datetime.now().isoformat()  # Обновляем активность при получении сообщения (чтобы бот не отвечал на 1 одно сообщение потом, если его перебили), однако, он не ответит на него, если не придет новое сообщение
            )
            logger.debug(f"[SESSION INTERATION] Message added to queue (queue size={len(message_queue)}) | session_id={session_id} | user_id={user_id}")
            return
        
        # Отменяем предыдущие таймеры
        for timer_name in ['inactivity_timer', 'processing_timer']:
            if timer := data.get(timer_name):
                logger.debug(f"[SESSION INTERATION] Cancelling previous {timer_name} | session_id={session_id} | user_id={user_id}")
                await timer.cancel()
                
        # Проверяем, активна ли ещё сессия
        if not await session_manager.is_session_active(db_user.id, session):
            logger.warning(f"[SESSION INTERATION] Session is no longer active | session_id={session_id} | user_id={user_id}")
            await end_session_cleanup(message, state, session, session_manager)
            return
        
        # Добавляем сообщение в очередь
        message_queue = deque(data.get("message_queue", []))
        message_queue.append(message.text)
        
        # Создаем новые таймеры
        inactivity_timer = SafeTimer("inactivity", state)
        processing_timer = SafeTimer("processing", state)
        
        timer_manager.add_timer(session_id, 'inactivity_timer', inactivity_timer)
        timer_manager.add_timer(session_id, 'processing_timer', processing_timer)
        
        # Обновляем состояние
        await state.update_data(
            message_queue=list(message_queue),
            is_bot_responding=True,
            last_activity=datetime.now().isoformat()
        )
        
        # Запускаем таймеры
        await processing_timer.start(PROCESSING_DELAY, process_messages_after_delay, state, message, session, session_manager, PROCESSING_DELAY, bot, timer_manager)
        await inactivity_timer.start(INACTIVITY_DELAY, check_inactivity, state, message, INACTIVITY_DELAY, session, session_manager, bot, timer_manager)
        
        logger.debug(f"[SESSION INTERATION] Timers started | session_id={session_id} | user_id={user_id}")
        
        