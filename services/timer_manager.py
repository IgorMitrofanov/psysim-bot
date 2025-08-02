from typing import Dict, Optional
import asyncio
from collections import defaultdict
from aiogram.fsm.context import FSMContext
from config import logger
    
    
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
            
            
class TimerManager:
    _instance = None
    _timers: Dict[str, Dict[str, SafeTimer]] = defaultdict(dict)
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def add_timer(cls, session_id: str, timer_name: str, timer: SafeTimer):
        cls._timers[session_id][timer_name] = timer
    
    @classmethod
    def get_timer(cls, session_id: str, timer_name: str) -> Optional[SafeTimer]:
        return cls._timers[session_id].get(timer_name)
    
    @classmethod
    async def cancel_timer(cls, session_id: str, timer_name: str):
        if timer := cls._timers[session_id].get(timer_name):
            await timer.cancel()
            del cls._timers[session_id][timer_name]
    
    @classmethod
    async def cancel_all_timers(cls, session_id: str):
        for timer_name, timer in list(cls._timers[session_id].items()):
            await timer.cancel()
            del cls._timers[session_id][timer_name]
    
    @classmethod
    def has_timer(cls, session_id: str, timer_name: str) -> bool:
        return timer_name in cls._timers[session_id]