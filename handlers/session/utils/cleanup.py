from handlers.session.utils.timer_and_lock import session_lock
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from collections import deque
from database.crud import get_user
from states import MainMenu
from services.session_manager import SessionManager
from config import logger
from .timer_and_lock import SafeTimer


async def end_session_cleanup(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
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

            # Отменяем все таймеры и очищаем их из состояния
            timer_names = ['inactivity_timer', 'processing_timer']
            cancelled_timers = 0
            for timer_name in timer_names:
                timer:SafeTimer = None
                if timer := data.get(timer_name):
                    logger.debug(f"[SESSION INTERATION] Cancelling {timer_name} | session_id={session_id} | user_id={user_id}")
                    try:
                        if not timer.completed and not timer.cancelled:
                            await timer.cancel()
                            cancelled_timers += 1
                    except Exception as e:
                        logger.error(f"[SESSION INTERATION] Error cancelling {timer_name}: {e} | session_id={session_id} | user_id={user_id}")

            # Очищаем ссылки на таймеры в состоянии
            await state.update_data({
                'inactivity_timer': None,
                'processing_timer': None,
                'message_queue': deque(),
                'is_bot_responding': False
            })
            
            logger.debug(f"[SESSION INTERATION] Cancelled {cancelled_timers}/{len(timer_names)} timers | session_id={session_id} | user_id={user_id}")
            
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