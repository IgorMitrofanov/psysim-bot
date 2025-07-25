import asyncio
import logging
from typing import Optional, Callable

from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)

class SafeTimer:
    def __init__(self, timeout: int, callback: Callable, name: str = ""):
        self._timeout = timeout
        self._callback = callback
        self._task: Optional[asyncio.Task] = None
        self._name = name

    def start(self):
        self.cancel()  # отменяем старый, если есть
        self._task = asyncio.create_task(self._run())
        logger.debug(f"Timer '{self._name}' started for {self._timeout} sec")

    def cancel(self):
        if self._task and not self._task.done():
            self._task.cancel()
            logger.debug(f"Timer '{self._name}' cancelled")

    async def _run(self):
        try:
            await asyncio.sleep(self._timeout)
            await self._callback()
        except asyncio.CancelledError:
            logger.debug(f"Timer '{self._name}' was cancelled before timeout")

class TimerManager:
    def __init__(self, state: FSMContext):
        self.state = state
        self.timers: dict[str, SafeTimer] = {}

    async def set_timer(self, name: str, timeout: int, callback: Callable):
        timer = SafeTimer(timeout, callback, name)
        timer.start()
        self.timers[name] = timer
        await self.state.update_data({f"{name}_timer": timer})

    async def cancel_timer(self, name: str):
        timer = self.timers.get(name)
        if timer:
            timer.cancel()
            self.timers[name] = None
            await self.state.update_data({f"{name}_timer": None})

    async def cancel_all(self):
        for name, timer in self.timers.items():
            if timer:
                timer.cancel()
        self.timers.clear()
        await self.state.update_data({
            'inactivity_timer': None,
            'processing_timer': None,
            'response_timer': None
        })
