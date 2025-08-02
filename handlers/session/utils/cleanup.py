from handlers.session.utils.lock import session_lock
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from collections import deque
from database.crud import get_user
from states import MainMenu
from services.session_manager import SessionManager
from config import logger
from services.timer_manager import TimerManager


async def end_session_cleanup(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager,
    timer_manager: TimerManager
):
    """Функция для корректного завершения сессии с гарантированным сбросом таймеров и состояния"""
    data = await state.get_data()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    logger.info(f"[SESSION INTERATION] Ending session cleanup has started | session_id={session_id} | user_id={user_id}")
    
    async with session_lock(state):
        try:
            # Ждем завершения ответа бота, если он в процессе
            while data.get("is_bot_responding", False):
                logger.debug(f"[SESSION INTERATION] Waiting for bot to finish responding | session_id={session_id} | user_id={user_id}")
                await asyncio.sleep(5)
                data = await state.get_data()

            # Отменяем все таймеры через менеджер
            logger.debug(f"[SESSION INTERATION] Cancelling all timers via manager | session_id={session_id} | user_id={user_id}")
            await timer_manager.cancel_all_timers(session_id)
            
            # Очищаем состояние
            await state.update_data({
                'message_queue': [],
                'is_bot_responding': False
            })
            
            # Завершаем сессию
            db_user = await get_user(session, telegram_id=message.from_user.id)
            if session_id and db_user:
                logger.debug(f"[SESSION INTERATION] Ending session in manager | session_id={session_id} | user_id={user_id}")
                try:
                    await session_manager.end_session(
                        user_id=db_user.id,
                        db_session=session,
                        session_id=session_id
                    )
                    logger.info(f"[SESSION INTERATION] Session ended successfully | session_id={session_id} | user_id={user_id}")
                except Exception as e:
                    logger.error(f"[SESSION INTERATION] Error ending session in manager: {e} | session_id={session_id} | user_id={user_id}")
            
            # Очищаем состояние
            logger.debug(f"[SESSION INTERATION] Clearing state | session_id={session_id} | user_id={user_id}")
            await state.clear()
            await state.set_state(MainMenu.choosing)
            logger.info(f"[SESSION INTERATION] Session cleanup completed | session_id={session_id} | user_id={user_id}")
        except Exception as e:
            logger.error(f"[SESSION INTERATION] Error during session cleanup: {e} | session_id={session_id} | user_id={user_id}")
            raise