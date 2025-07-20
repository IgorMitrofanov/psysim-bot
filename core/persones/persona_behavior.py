import random
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from core.persones.llm_engine import get_response
from core.persones.prompt_builder import build_prompt
from config import logger

class PersonaBehavior:
    def __init__(self, persona_data, resistance_level=None, emotional_state=None, format=None):
        self.persona_data = persona_data
        self.name = persona_data['persona']['name']
        self.resistance_level = resistance_level
        self.emotional_state = emotional_state
        self.format = format
        self.history = []

        # Сохраняем min/max задержку и длину
        guide = persona_data.get("interaction_guide", {})
        self.min_delay = guide.get("reply_delay_sec", {}).get("min", 0)
        self.max_delay = guide.get("reply_delay_sec", {}).get("max", 2)
        
        # Настройки буферизации и реакции на молчание
        self.message_buffer: List[str] = []
        self.last_interaction_time: Optional[datetime] = None
        self.silence_threshold = timedelta(seconds=30)  # Порог молчания
        self.buffer_window = timedelta(seconds=10)  # Окно для накопления сообщений
        
        # Настройки вероятности ответа
        self.base_response_prob = 0.8  # Базовая вероятность ответа
        self.silence_response_prob = 0.75  # Вероятность ответа после молчания
        
    def _get_emotion_delay_factor(self) -> float:
        """Возвращает множитель задержки в зависимости от эмоции"""
        factors = {
            "emotion_anxious": 1.2,   
            "emotion_aggressive": 0.7,
            "emotion_cold": 1.5,
            "emotion_shocked": 1.0,
            "emotion_breakdown": 0.9,
            "emotion_superficial": 0.8
        }
        return factors.get(self.emotional_state, 1.0)

    def _get_resistance_response_prob(self) -> float:
        """Вероятность ответа в зависимости от уровня сопротивления"""
        if self.resistance_level == "высокий":
            return 0.6  # 60% шанс ответа
        return 0.9       # 90% шанс при среднем уровне сопротивления
    
    def _should_respond(self) -> bool:
        """Определяет, нужно ли отвечать на сообщение"""
        # Всегда отвечаем на первое сообщение
        if not self.history:
            return True
            
        # Проверяем вероятность ответа
        response_prob = self.base_response_prob * self._get_resistance_response_prob()
        return random.random() <= response_prob
    
    
    async def check_silence(self) -> Optional[Tuple[str, int]]:
        """Проверяет молчание и возвращает ответ"""
        if not self.last_interaction_time:
            return None
            
        silence_duration = datetime.now() - self.last_interaction_time
        if silence_duration < self.silence_threshold:
            return None
            
        if random.random() > self.silence_response_prob:
            return None

        # Генерируем реакцию на молчание
        prompt = [{
            "role": "system",
            "content": f"Терапевт на сессии молчит {silence_duration.seconds} секунд. Напиши ему свою реакцию, так как сказал бы пациент."
        }]
        
        reply, tokens_used = await get_response(prompt)
        self.history.append({"role": "assistant", "content": reply})
        self.last_interaction_time = datetime.now()
        
        return reply, tokens_used
    
    def _salt_prompt(self, prompt: List[Dict]) -> List[Dict]:
        """Модифицирует промпт перед отправкой в LLM"""
        return [{
            "role": "user",
            "content": f"Теравет говорит вам: {msg['content']}"
        } if msg["role"] == "user" else msg for msg in prompt]

    async def send(self, user_message: str) -> Optional[Tuple[str, int]]:
        """Обрабатывает сообщение пользователя и возвращает ответ"""
        # Добавляем сообщение пользователя в буфер, и смотрим сколько прошло с последнего ответа
        now = datetime.now()
        self.message_buffer.append(user_message)
        self.last_interaction_time = now

        prompt = []
        
        # Если не нужно отвечать - выходим
        if not self._should_respond():
            return None

        # Объединяем сообщения из буфера
        combined_message = "\n".join(self.message_buffer)
        self.message_buffer.clear()
        
        # Добавляем в историю
        self.history.append({"role": "user", "content": combined_message})

        # Инициализируем system prompt при первом сообщении
        if not any(msg["role"] == "system" for msg in self.history):
            self.history.insert(0, {
                "role": "system",
                "content": build_prompt(
                    self.persona_data,
                    resistance_level=self.resistance_level,
                    emotional_state=self.emotional_state,
                )
            })

        # Задержка ответа с учетом эмоции
        delay = random.uniform(
            self.min_delay * self._get_emotion_delay_factor(),
            self.max_delay * self._get_emotion_delay_factor()
        )
        await asyncio.sleep(delay)

        if self.history:
            last_patient_reply = self.history[-1]
            if last_patient_reply["role"] == "assistant":
                prompt.append(last_patient_reply)
        logger.info(f"Prompt before salting {prompt}")
        prompt = self._salt_prompt(prompt)
        logger.info(f"Prompt after salting {prompt}")

        # Получаем ответ от LLM
        reply, tokens_used = await get_response(prompt)
        self.history.append({"role": "assistant", "content": reply})

        return reply, tokens_used

    def reset(self, resistance_level=None, emotional_state=None, format=None):
        self.history.clear()
        if resistance_level:
            self.resistance_level = resistance_level
        if emotional_state:
            self.emotional_state = emotional_state
        if format:
            self.format = format
            

    def get_history(self):
        """Возвращает историю в виде списка сообщений."""
        return self.history