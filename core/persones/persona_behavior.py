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

    async def send(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})

        # Строим system prompt только один раз
        if not any(msg["role"] == "system" for msg in self.history):
            self.history.insert(0, {
                "role": "system",
                "content": build_prompt(
                    self.persona_data,
                    resistance_level=self.resistance_level,
                    emotional_state=self.emotional_state,
                )
            })

        # Задержка перед ответом
        delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)

        # Подготавливаем prompt: только последние 6 сообщений
        trimmed = self.history[-6:] if len(self.history) > 6 else self.history

        # Подсаливаем: переименовываем user-сообщения
        salted_prompt = []
        for msg in trimmed:
            if msg["role"] == "user":
                salted_prompt.append({
                    "role": "user",
                    "content": f"Теравет говорит: {msg['content']}"
                })
            else:
                salted_prompt.append(msg)

        # Получаем ответ от LLM
        reply = await get_response(salted_prompt)

        # Сохраняем обычный ответ в историю
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