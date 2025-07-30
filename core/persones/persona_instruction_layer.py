from typing import Dict, List, Tuple

from config import logger
from core.persones.llm_engine import get_response, call_llm_for_meta_ai
from core.persones.prompt_builder import build_humalizate_prompt


SALTER_LAYER_TEMP = 0.9

class PersonaSalterLayer:
    def __init__(self, persona_data: Dict, resistance_level: str, emotional_state: str,):
        """
        Initialize the LLM salter with persona data and optional recent decisions history.
        
        Args:
            persona_data: Dictionary containing persona information
            recent_decisions: List of recent decisions made by the system
        """
        self.persona_data = persona_data
        self.resistance_level = resistance_level
        self.emotional_state = emotional_state

    async def salt_message(
        self,
        user_message: str,
        strategy: str,
        recent_decisions: List[str],
        history: List[Dict]
    ) -> Tuple[str, int]:
        """
        Add contextual "salt" to a message using LLM.
        
        Args:
            user_message: The original message to salt
            strategy: Current response strategy
            resistance_level: Patient's resistance level
            emotional_state: Patient's emotional state
            history: Conversation history
            
        Returns:
            Tuple of (salted message, estimated token count)
        """
        try:
            last_decisions = "\n".join(f"{i+1}. {d}" for i, d in enumerate(recent_decisions))
            salt_phrase = await self._generate_salt_phrase(
                strategy=strategy,
                user_message=user_message,
                resistance_level=self.resistance_level,
                emotional_state=self.emotional_state,
                last_decisions=last_decisions,
                history=history
            )
            
            prompt = f"""
            Сообщение терапевта:
            "{user_message}"
            
            Инструкция:
            *{salt_phrase}*

            Принятое решение на шаге: 
            
            *{strategy}*

            Хронология решений: 
            
            {last_decisions}

            """
            
            tokens = len(prompt) // 4 
            logger.info(f"[AI-salter-layer] Salted message: {prompt}, tokens used: {tokens}")
            return prompt, tokens
            
        except Exception as e:
            logger.error(f"[AI-salter-layer] Error in salting message: {str(e)}", exc_info=True)
            return user_message, 0

    async def _generate_salt_phrase(
        self,
        strategy: str,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        last_decisions: List[str],
        history: List[Dict]
    ) -> str:
        """Генерирует контекстно-зависимую фразу для подсолки через LLM"""
        history_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history[-3:]
        )
        
        persona = self.persona_data.get('persona', {})
        profile = self.persona_data.get('personality_profile', {})
        
        basic_info = [
        f"Имя: {persona.get('name', '—')}",
        f"Возраст: {persona.get('age', '—')}",
        f"Профессия: {persona.get('profession', '—')}",
        f"Семейное положение: {persona.get('marital_status', '—')}",
        f"Жилищные условия: {persona.get('living_situation', '—')}",
        f"Образование: {persona.get('education', '—')}"
        ]
        
        system_prompt = f"""
        Ты психологический ассистент, помогающий формировать естественные ответы пациента в терапии.
        Сгенерируй краткую (1-2 предложения), конкретную инструкцию для ответа пациента.

        Тебе будет отправлена выбранная стратегия ответа:

        1. respond — стандартный ответ
        2. escalate — эмоциональная реакция
        3. self_report — самоанализ
        4. silence — пауза
        5. disengage — завершение сессии, возможно была агрессия, холод, незаинтересованность
        6. shift_topic — перевод темы
        7. open_up — углубление в терапию

        Учитывай, что shift_topic — это защитная стратегия (избегание), а open_up — признак доверия и снижения сопротивления.

        Информация о пациенте:
        Имя: {persona.get('name', 'Неизвестный')}
        Возраст: {persona.get('age', '?')}
        Стиль привязанности: {profile.get('attachment_style', 'не определен')}
        Преобладающие схемы: {', '.join(profile.get('predominant_schemas', [])) if profile.get('predominant_schemas') else 'нет данных'}
        
        # ОСНОВНАЯ ИНФОРМАЦИЯ:
         {"\n".join(basic_info)}
    
        """
        
        tone_data = self.persona_data.get("tone", {})
        defenses = profile.get("defense_mechanisms", {})

        user_prompt = f"""
        Контекст:
        - Стратегия ответа: {strategy}
        - Текущее сопротивление: {resistance_level}
        - Эмоциональное состояние: {emotional_state}
        - Механизмы защиты: {', '.join(defenses.keys()) if defenses else 'не определены'}
        
        Стиль общения:
        - Базовый: {tone_data.get("baseline", "—")}
        - При защите: {tone_data.get("defensive_reaction", "—")}
        

        Хронология решений: 
        {last_decisions}

        Про персонажа:
        - Поведенческие правила: {', '.join(self.persona_data.get('behaviour_rules', [])) if self.persona_data.get('behaviour_rules') else 'нет'}
        - Типичные самоотчеты: {', '.join(self.persona_data.get('self_reports', [])) if self.persona_data.get('self_reports') else 'нет'}
        - Триггеры: {', '.join(self.persona_data.get('triggers', [])) if self.persona_data.get('triggers') else 'нет'}

        История последних сообщений:
        {history_text}
        
        Новое сообщение терапевта:
        "{user_message}"
        
        Сгенерируй только саму инструкцию для пациента, без пояснений.
        Учитывай особенности персонажа, его защитные механизмы и текущее состояние.
        ВАЖНО: не давай четкую фразу для ответа, напиши инструкцию так, чтобы пациент сам придумал ответ и терапия развивалась или не развивалась в зависимости от профессинализма терапевта.
        """
        
        response, _ = await call_llm_for_meta_ai(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=SALTER_LAYER_TEMP
        )
        
        return response