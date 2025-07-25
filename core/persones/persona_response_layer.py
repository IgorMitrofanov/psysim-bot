from config import logger
from typing import Dict
from config import logger
from core.persones.prompt_builder import build_prompt
from core.persones.llm_engine import get_response


class PersonaResponseLayer:
    def __init__(self, persona_data: Dict, resistance_level: str, emotional_state: str):
        """
        Инициализация обработчика ответов для персонажа.
        
        Args:
            persona_data: Данные персонажа
            resistance_level: Уровень сопротивления
            emotional_state: Эмоциональное состояние
        """
        self.persona_data = persona_data
        self.resistance_level = resistance_level
        self.emotional_state = emotional_state
        system_prompt = build_prompt(
                    persona_data,
                    resistance_level=resistance_level,
                    emotional_state=emotional_state,
                )
        self.main_history = []
        self.main_history.insert(0, {"role": "system", "content": system_prompt})
        logger.info("[AI-response-layer] Added system prompt to history")

    async def get_response(self):
        response, tokens_used = await get_response(self.main_history)
        logger.info(f"[AI-response-layer] LLM response: {response}, tokens used: {tokens_used}")
        return response, tokens_used
        
    def update_history(self, msg, is_user=True):
        if is_user:
            self.main_history.append({"role": "user", "content": msg})
        else:
            self.main_history.append({"role": "assistant", "content": " ".join(msg)})
        logger.info(f"[AI-response-layer] Main history updated, new history: {self.main_history}")