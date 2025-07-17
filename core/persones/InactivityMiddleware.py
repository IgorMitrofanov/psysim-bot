from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable

class InactivityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        state = data.get('state')
        state_data = await state.get_data()
        
        # Если пользователь в сессии
        if await state.get_state() == MainMenu.in_session:
            persona = state_data.get('persona')
            last_message_time = state_data.get('last_message_time', datetime.utcnow())
            
            # Проверяем время бездействия
            if (datetime.utcnow() - last_message_time) > timedelta(minutes=2):  # 2 минуты бездействия
                if persona:
                    response = await persona.handle_inactivity()
                    await event.answer(response)
                    await state.update_data(last_message_time=datetime.utcnow())
        
        await state.update_data(last_message_time=datetime.utcnow())
        return await handler(event, data)
    
# router.message.middleware(InactivityMiddleware())


@router.message(MainMenu.in_session)
@check_session_timeout()
async def session_interaction_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    persona: PersonaBehavior = data.get("persona")
    if not persona:
        await message.answer("Ошибка: персонаж не найден.")
        return

    # Обновляем время последнего сообщения
    await state.update_data(last_message_time=datetime.utcnow())
    
    # Обработка сообщения
    response = await persona.send(message.text)
    await message.answer(response)
    
    
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from core.persones.llm_engine import get_response
from core.persones.prompt_builder import build_prompt


class PersonaBehavior:
    def __init__(self, persona_data, resistance_level=None, emotional_state=None):
        self.persona_data = persona_data
        self.name = persona_data['persona']['name']
        self.resistance_level = resistance_level or "средний"
        self.emotional_state = emotional_state or "нейтральное"
        self.history = []
        self.last_interaction_time = datetime.utcnow()

        # Параметры взаимодействия
        guide = persona_data.get("interaction_guide", {})
        self.min_delay = guide.get("reply_delay_sec", {}).get("min", 0)
        self.max_delay = guide.get("reply_delay_sec", {}).get("max", 2)
        self.min_chars = guide.get("message_length", {}).get("min_chars", 30)
        self.max_chars = guide.get("message_length", {}).get("max_chars", 200)
        
        # Параметры для инициативы и реакции на молчание
        self.initiative_chance = guide.get("initiative_chance", 0.3)  # 30% шанс начать диалог
        self.inactivity_threshold = timedelta(minutes=2)  # Порог молчания
        self.inactivity_responses = guide.get("inactivity_responses", [
            "Вы всё ещё здесь?",
            "Мне интересно ваше мнение...",
            "Продолжим наш разговор?"
        ])

    async def send(self, user_message: Optional[str] = None) -> str:
        # Обновляем время последнего взаимодействия
        self.last_interaction_time = datetime.utcnow()
        
        if user_message:
            self.history.append({"role": "user", "content": user_message})

        # Создаём system prompt с текущими состояниями
        system_prompt = build_prompt(
            self.persona_data,
            resistance_level=self.resistance_level,
            emotional_state=self.emotional_state,
            is_initiative=user_message is None  # Флаг, что это инициативное сообщение
        )

        # Собираем prompt (последние 5 сообщений + system)
        prompt = [{"role": "system", "content": system_prompt}] + self.history[-5:]

        # Задержка перед ответом
        delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)

        # Получаем ответ
        reply = await get_response(prompt)

        # Добавляем ответ в историю
        self.history.append({"role": "assistant", "content": reply})

        return reply

    async def check_inactivity(self) -> Optional[str]:
        """Проверяет молчание пользователя и возвращает ответ или None"""
        if datetime.utcnow() - self.last_interaction_time > self.inactivity_threshold:
            # Выбираем случайный ответ из заготовленных
            return random.choice(self.inactivity_responses)
        return None

    async def take_initiative(self) -> Optional[str]:
        """Пытается начать диалог, возвращает сообщение или None"""
        if random.random() < self.initiative_chance:
            return await self.send()  # Отправляем без сообщения пользователя
        return None

    def reset(self, resistance_level=None, emotional_state=None):
        self.history.clear()
        if resistance_level:
            self.resistance_level = resistance_level
        if emotional_state:
            self.emotional_state = emotional_state
        self.last_interaction_time = datetime.utcnow()

    def get_history(self):
        return self.history
    
    
async def handle_inactivity(self) -> str:
    self.history.append({"role": "user", "content": "(пользователь молчит слишком долго)"})

    system_prompt = build_prompt(
        self.persona_data,
        resistance_level=self.resistance_level,
        emotional_state=self.emotional_state,
    )
    prompt = [{"role": "system", "content": system_prompt}] + self.history[-5:]
    
    reply = await get_response(prompt)
    self.history.append({"role": "assistant", "content": reply})
    return reply


from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable
from datetime import datetime, timedelta
from states import MainMenu

class InactivityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        state = data.get('state')
        if not state:
            return await handler(event, data)

        state_data = await state.get_data()

        if await state.get_state() == MainMenu.in_session:
            persona = state_data.get('persona')
            last_message_time = state_data.get('last_message_time', datetime.utcnow())
            
            if (datetime.utcnow() - last_message_time) > timedelta(minutes=2):
                if persona:
                    response = await persona.handle_inactivity()
                    await event.answer(response)
                    await state.update_data(last_message_time=datetime.utcnow())

        await state.update_data(last_message_time=datetime.utcnow())
        return await handler(event, data)
