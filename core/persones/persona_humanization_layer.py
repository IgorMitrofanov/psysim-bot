from config import config, logger
from openai import OpenAI
import asyncio
from typing import Dict, List, Tuple

from config import logger
from core.persones.llm_engine import call_llm_for_meta_ai
from core.persones.prompt_builder import build_humalizate_prompt


class PersonaHumanizationLayer:
    def __init__(self, persona_data: Dict, resistance_level: str, emotional_state: str,):
        self.persona_data = persona_data
        self.resistance_level = resistance_level
        self.emotional_state = emotional_state
         
    async def humanization_respond(
            self, 
            raw_response: str, 
            history: List[Dict]
        ) -> Tuple[str, int]:
            """
            Refines raw LLM response to match character's style and personality.
            
            Args:
                raw_response: Raw response from LLM
                history: Conversation history
                
            Returns:
                Tuple of (refined response, tokens used)
            """
            try:
                humanization_prompt = build_humalizate_prompt(
                    self.persona_data, 
                    raw_response, 
                    history, 
                    self.resistance_level, 
                    self.emotional_state
                )

                system_msg = "Ты эксперт по адаптации текста под стиль речи. Сохраняй смысл, меняй форму. Делай текст, в зависимости от портерета личности. Иногда можно писать с маленькой буквы и т д. Учитывай, какие языки знает персонаж. Можно разделять ответ через || для эффекта живой речи. Не делай много разделей слишком часто, чтобы разговор казался живым. Следи за историей сообщений, твои сообщения - assistant, терапевта - <Сообщение терапевта>"

                refined_response, tokens_used = await call_llm_for_meta_ai(
                    system_prompt=system_msg,
                    user_prompt=humanization_prompt,
                    temperature=0.8
                )
                
                # refined_response = refined_response.replace("`", "").replace("-", "")
                logger.debug(f"[AI-decision system] Refined response: {refined_response[:200]}...")
                
                return refined_response.strip(), tokens_used
                
            except Exception as e:
                logger.error(f"[AI-decision system] Error refining response: {str(e)}", exc_info=True)
                return raw_response, 0