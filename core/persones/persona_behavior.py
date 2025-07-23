import random
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from core.persones.llm_engine import get_response
from core.persones.prompt_builder import build_prompt, build_humalizate_prompt
from core.persones.persona_decision_system import PersonaDecisionSystem
import json
from config import logger

HUMANIZATION_TEMP = 0.9


class PersonaBehavior:
    def __init__(self, persona_data, resistance_level=None, emotional_state=None, format=None):
        self.persona_data = persona_data
        self.name = persona_data['persona']['name']
        self.resistance_level = resistance_level or "resistance_medium"
        self.emotional_state = emotional_state or "emotion_neutral"
        self.format = format
        self.history = []
        
        self.typing_callback = None
        
        # Инициализация подсистем
        self.decision_system = PersonaDecisionSystem(persona_data)
        
        # Настройка временных параметров из данных персонажа
        guide = persona_data.get("interaction_guide", {})
        self.min_delay = guide.get("reply_delay_sec", {}).get("min", 0)
        self.max_delay = guide.get("reply_delay_sec", {}).get("max", 2)

        
        logger.info(f"Initialized PersonaBehavior for {self.name} with resistance: {self.resistance_level}, "
                   f"emotion: {self.emotional_state}, delay: {self.min_delay}-{self.max_delay}s")
        
    def set_typing_callback(self, callback):
        """Устанавливает callback для индикатора печатания"""
        self.typing_callback = callback

    async def _start_typing_indicator(self):
        """Запускает индикатор печатания, если callback установлен"""
        if self.typing_callback:
            return asyncio.create_task(self.typing_callback())
        return None
        
    async def _refine_response_with_style(self, raw_response: str, history: list[str]) -> Tuple[str, int]:
        """
        Преобразует сырой ответ от базовой LLM в стилизованный под персонажа вариант.
        Возвращает обработанный ответ и количество использованных токенов.
        """
        humanization_prompt, system_msg = build_humalizate_prompt(self.persona_data, raw_response, history, self.resistance_level, self.emotional_state)
        messages = [{"role": "system", "content": system_msg}, {"role": "user", "content": humanization_prompt}]
        
        refined_response, tokens_used = await get_response(messages, temperature=HUMANIZATION_TEMP)
        # Удалим мусор, приходится жертвовать тире и ковычками такими, т.к. бывает модели высерают
        refined_response = refined_response.replace("`", "")
        refined_response = refined_response.replace("-", "")
        
        return refined_response.strip(), tokens_used


    async def send(self, user_message: str) -> Tuple[str, Optional[str], int]:
        total_tokens = 0

        # Обрабатываем сообщение через систему принятия решений
        decision, processed_msg, decision_tokens = await self.decision_system.process_user_message(
            user_message,
            self.resistance_level,
            self.emotional_state,
            self.history
        )
        total_tokens += decision_tokens
        
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
            self.history.append({"role": "assistant", "content": "*молчание, ваш персонаж (пациент) предпочел не отвечать*"})
            return decision, None, total_tokens
        elif decision == 'disengage':
            try:
                logger.info(f"{self.name} decided to disengage")
                typing_task = await self._start_typing_indicator()
                self.history.append({"role": "assistant", "content": "*Персонаж покидает сессию* " + processed_msg})
                return decision, processed_msg, total_tokens
            finally:
                if typing_task and not typing_task.done():
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass
        else:
        # Добавляем обработанное сообщение в историю
            try:
                typing_task = await self._start_typing_indicator()
                if processed_msg:
                    self.history.append({"role": "user", "content": processed_msg})
                    logger.debug(f"Added message to history: {processed_msg[:50]}...")
                
                # Имитация задержки ответа
                delay = random.uniform(self.min_delay, self.max_delay)
                logger.info(f"Simulating thinking delay: {delay:.2f}s")
                await asyncio.sleep(delay)
                
                #  Получение ответа от LLM
                logger.debug(f"Sending to LLM. Last messages: {json.dumps(self.history, ensure_ascii=False)}")
                response, response_tokens = await get_response(self.history)
                total_tokens += response_tokens
                logger.info(f"Final LLM response: {response}")
                # Очеловечивание — вторичная генерация с сохранением смысла
                refined_response, refined_tokens = await self._refine_response_with_style(response, self.history)
                total_tokens += refined_tokens

                response = refined_response 
                logger.info(f"Final LLM response (with humanization): {response}")
                logger.info(f"Received response from LLM. Tokens: {response_tokens}, response: {response[:100]}...")
                
                # Разделение ответа на части по ||
                if "||" in refined_response:
                    response_parts = [part.strip() for part in refined_response.split("||") if part.strip()]
                    logger.info(f"Split response into parts: {response_parts}")
                else:
                    response_parts = [refined_response]
                
                # Обновление истории (сохраняем как единое сообщение)
                self.history.append({"role": "assistant", "content": " ".join(response_parts)})
                
                
                logger.info(f"{self.name} response complete. Total tokens used: {total_tokens}")
                return decision, response_parts, total_tokens
            finally:
                if typing_task and not typing_task.done():
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass