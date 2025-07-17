import random
import asyncio
from core.persones.llm_engine import get_response
from core.persones.prompt_builder import build_prompt


class PersonaBehavior:
    def __init__(self, persona_data, resistance_level=None, emotional_state=None):
        self.persona_data = persona_data
        self.name = persona_data['persona']['name']
        self.resistance_level = resistance_level or "средний"
        self.emotional_state = emotional_state or "нейтральное"
        self.history = []

        # Сохраняем min/max задержку и длину
        guide = persona_data.get("interaction_guide", {})
        self.min_delay = guide.get("reply_delay_sec", {}).get("min", 0)
        self.max_delay = guide.get("reply_delay_sec", {}).get("max", 2)

        self.min_chars = guide.get("message_length", {}).get("min_chars", 30)
        self.max_chars = guide.get("message_length", {}).get("max_chars", 200)

    async def send(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})

        # Создаём system prompt с текущими состояниями
        system_prompt = build_prompt(
            self.persona_data,
            resistance_level=self.resistance_level,
            emotional_state=self.emotional_state,
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

    def reset(self, resistance_level=None, emotional_state=None):
        self.history.clear()
        if resistance_level:
            self.resistance_level = resistance_level
        if emotional_state:
            self.emotional_state = emotional_state

    def get_history(self):
        """Возвращает историю в виде списка сообщений."""
        return self.history