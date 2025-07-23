import random
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from core.persones.llm_engine import get_response
from core.persones.prompt_builder import build_prompt
from core.persones.persona_decision_system import PersonaDecisionSystem
# from core.persones.meta_memory_system import MetaMemorySystem
import json
from config import logger


class PersonaBehavior:
    def __init__(self, persona_data, resistance_level=None, emotional_state=None, format=None):
        self.persona_data = persona_data
        self.name = persona_data['persona']['name']
        self.resistance_level = resistance_level or "resistance_medium"
        self.emotional_state = emotional_state or "emotion_neutral"
        self.format = format
        self.history = []
        
        # Инициализация подсистем
        self.decision_system = PersonaDecisionSystem(persona_data)
        # self.meta_memory = MetaMemorySystem(persona_data)
        
        # Настройка временных параметров из данных персонажа
        guide = persona_data.get("interaction_guide", {})
        self.min_delay = guide.get("reply_delay_sec", {}).get("min", 0)
        self.max_delay = guide.get("reply_delay_sec", {}).get("max", 2)

        
        logger.info(f"Initialized PersonaBehavior for {self.name} with resistance: {self.resistance_level}, "
                   f"emotion: {self.emotional_state}, delay: {self.min_delay}-{self.max_delay}s")
        
    async def refine_response_with_style(self, raw_response: str, history: list[str]) -> Tuple[str, int]:
        """
        Преобразует сырой ответ от базовой LLM в стилизованный под персонажа вариант.
        """
        style_prompt = build_prompt(
            self.persona_data,
            resistance_level=self.resistance_level,
            emotional_state=self.emotional_state
        )

        prompt = f"""{style_prompt}

    ---

    Теперь прими следующий исходный текст как ответ твоего персонажа, суть сохраняй, но напиши его так, 
    как сказал бы этот персонаж — с учетом его характера, стиля, эмоций и текущего состояния.

    Можно добавить ошибок орфографических, использовать нецензурную лексику, если биография позволяет.

    Можно имитировать ошибки набора через Т9, опечатки - если сообщение эомциональное. Поступай в зависимости от контекста

    Говори через примеры из жизни, исходя из твоего реального опыта, биографии.

    
    # Контекст сессии ( ты "assistant" - пациент, "user" - психотерапевт
    История последних сообщений:
    {history}

    Исходный ответ:
    \"\"\"{raw_response}\"\"\"
    """

        # Можно использовать ту же LLM, но с другим system prompt
        refined_response, tokens_used = await get_response([{"role": "system", "content": prompt}], temperature=1.1)
        return refined_response, tokens_used


    async def send(self, user_message: str) -> Tuple[str, Optional[str], int]:
        """
        Основной метод обработки сообщения
        
        Возвращает:
        - Tuple[решение, ответ, количество токенов]
        - Если ответ None - персонаж молчит
        - Если решение 'disengage' - персонаж завершает сеанс


        # Доступные стратегии:
        1. respond — стандартный ответ
        2. escalate — эмоциональная реакция
        3. self_report — самоанализ
        4. silence — пауза
        5. disengage — завершение
        6. shift_topic — перевод темы
        7. open_up — углубление в терапию
        """
        total_tokens = 0
        logger.debug(f"Received message from user: {user_message[:100]}...")

        # Обрабатываем сообщение через систему принятия решений
        decision, processed_msg, decision_tokens = await self.decision_system.process_user_message(
            user_message,
            self.resistance_level,
            self.emotional_state,
            self.history
        )
        total_tokens += decision_tokens
        
        logger.info(f"Decision: {decision}, processed_msg: {'None' if processed_msg is None else processed_msg[:50]}...")
        
        # Системный промпт добавляется единожды
        if not any(msg["role"] == "system" for msg in self.history):
            system_prompt = build_prompt(
                self.persona_data,
                resistance_level=self.resistance_level,
                emotional_state=self.emotional_state,
            )
            self.history.insert(0, {"role": "system", "content": system_prompt})
            logger.debug("Added system prompt to history")
        
        # Обработка специальных решений
        if decision == 'silence':
            logger.info(f"{self.name} decided to remain silent")
            self.history.append({"role": "assistant", "content": "*молчание, ваш персонаж предпочел не отвечать*"})
            return decision, None, total_tokens
        elif decision == 'disengage':
            logger.info(f"{self.name} decided to disengage. Final message: {processed_msg[:100]}...")
            # Очеловечивание — вторичная генерация с сохранением смысла
            refined_response, refined_tokens = await self.refine_response_with_style(processed_msg, self.history)
            total_tokens += refined_tokens

            response = refined_response 
            logger.info(f"Final LLM response (with humanization): {response}")
            return decision, refined_response, total_tokens
            
        else:
        # Добавляем обработанное сообщение в историю
            if processed_msg:
                self.history.append({"role": "user", "content": processed_msg})
                logger.debug(f"Added message to history: {processed_msg[:50]}...")
            
            # 4. Имитация задержки ответа
            delay = random.uniform(self.min_delay, self.max_delay)
            logger.info(f"Simulating thinking delay: {delay:.2f}s")
            await asyncio.sleep(delay)
            
            # 5. Получение ответа от LLM
            logger.debug(f"Sending to LLM. Last messages: {json.dumps(self.history, ensure_ascii=False)}")
            response, response_tokens = await get_response(self.history)
            total_tokens += response_tokens
            logger.info(f"Final LLM response: {response}")
            # Очеловечивание — вторичная генерация с сохранением смысла
            refined_response, refined_tokens = await self.refine_response_with_style(response, self.history)
            total_tokens += refined_tokens

            response = refined_response 
            logger.info(f"Final LLM response (with humanization): {response}")
            logger.info(f"Received response from LLM. Tokens: {response_tokens}, response: {response[:100]}...")
            
            # 6. Обновление истории
            self.history.append({"role": "assistant", "content": response})
            logger.debug(f"Added assistant response to history. Total history length: {len(self.history)}")
            
            
            logger.info(f"{self.name} response complete. Total tokens used: {total_tokens}")
            return decision, response, total_tokens

    async def update_state(self, resistance_level: str = None, emotional_state: str = None):
        """Обновляет состояние персонажа"""
        if resistance_level:
            self.resistance_level = resistance_level
        if emotional_state:
            self.emotional_state = emotional_state
        
        # Обновляем мета-память при изменении состояния
        if resistance_level or emotional_state:
            _, _ = await self.meta_memory.update_memory(self.history)
            
        logger.info(f"Updated state for {self.name}. New resistance: {self.resistance_level}, emotion: {self.emotional_state}")

    def get_current_state(self) -> dict:
        """Возвращает текущее состояние персонажа"""
        return {
            'resistance': self.resistance_level,
            'emotion': self.emotional_state,
            'history_length': len(self.history),
            'memory_summary': self.meta_memory.get_compressed_memory()
        }