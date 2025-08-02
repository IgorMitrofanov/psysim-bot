from contextlib import asynccontextmanager
import asyncio
import time
from uuid import uuid4
from aiogram.fsm.context import FSMContext
from config import logger


@asynccontextmanager
async def session_lock(state: FSMContext):
    """
    Контекстный менеджер для безопасной блокировки сессии.
    Используется для предотвращения одновременного доступа к критическим секциям кода.
    """
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