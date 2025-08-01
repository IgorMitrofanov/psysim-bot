from contextlib import asynccontextmanager
import asyncio
import time
from uuid import uuid4
from typing import Optional
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

class SafeTimer:
    """Абстрактный класс для безопасного таймера с возможностью отмены и проверки состояния сессии"""
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
        logger.debug(f"[TIMER {self.name.upper()}] INITIALIZED | session_id={self.session_id} | user_id={self.user_id}")
    
    async def start(self, delay: float, callback, *args):
        """Запускает таймер"""
        await self.initialize()
        
        if self.task and not self.task.done():
            logger.warning(f"[TIMER {self.name.upper()}] CANCELLING PREVIOUS TASK | session_id={self.session_id} | user_id={self.user_id}")
            await self.cancel()
        
        self.cancelled = False
        self.completed = False
        
        async def timer_task():
            try:
                logger.debug(f"[TIMER {self.name.upper()}] STARTING | session_id={self.session_id} | user_id={self.user_id}")
                await asyncio.sleep(delay)
                
                if self.cancelled:
                    logger.debug(f"[TIMER {self.name.upper()}] CANCELLED BEFORE EXECUTION | session_id={self.session_id} | user_id={self.user_id}")
                    return
                
                # Проверяем актуальность сессии перед выполнением
                current_data = await self.state.get_data()
                if current_data.get('session_id') != self.session_id:
                    logger.warning(f"[TIMER {self.name.upper()}] SESSION CHANGED - CANCELLING | session_id={self.session_id} | user_id={self.user_id}")
                    return

                logger.debug(f"[TIMER {self.name.upper()}] EXECUTING CALLBACK | session_id={self.session_id} | user_id={self.user_id}")
                await callback(*args)
                self.completed = True
                logger.debug(f"[TIMER {self.name.upper()}] COMPLETED | session_id={self.session_id} | user_id={self.user_id}")
            except asyncio.CancelledError:
                logger.debug(f"[TIMER {self.name.upper()}] CANCELLED DURING EXECUTION | session_id={self.session_id} | user_id={self.user_id}")
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
            logger.debug(f"[TIMER {self.name.upper()}] CANCELLATION REQUESTED BUT TASK ALREADY DONE | session_id={self.session_id} | user_id={self.user_id}")
            return
            
        self.cancelled = True
        self.task.cancel()
        logger.debug(f"[TIMER {self.name.upper()}] CANCELLATION REQUESTED | session_id={self.session_id} | user_id={self.user_id}")
        
        try:
            await self.task
            logger.debug(f"[TIMER {self.name.upper()}] CANCELLATION CONFIRMED | session_id={self.session_id} | user_id={self.user_id}")
        except asyncio.CancelledError:
            logger.debug(f"[TIMER {self.name.upper()}] CANCELLATION CONFIRMED | session_id={self.session_id} | user_id={self.user_id}")
        except Exception as e:
            logger.error(f"[TIMER {self.name.upper()}] ERROR DURING CANCELLATION: {e} | session_id={self.session_id} | user_id={self.user_id}")