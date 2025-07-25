from typing import Dict, List, Tuple, Optional
import logging

from config import logger
from core.persones.llm_engine import call_llm_for_meta_ai

VALID_DECISIONS = {
    'respond', 
    'escalate', 
    'self_report', 
    'silence', 
    'disengage', 
    'shift_topic', 
    'open_up'
}

DECISION_LAYER_TEMP = 1.2

class PersonaDecisionLayer:
    """Мета слой принятия решений для психотерапевтического диалога.
    
    Может работать с любым персонажем, данные которого передаются при каждом вызове.
    """

    def __init__(self, persona_data: Dict, resistance_level: str, emotional_state: str,):
        """Инициализация сброшенного состояния."""
        self.reset()
        self.max_decision_history = 30
        self.persona_data = persona_data
        self.resistance_level = resistance_level
        self.emotional_state = emotional_state
        
    def reset(self):
        """Полностью сбрасывает состояние класса (историю решений)."""
        self.recent_decisions = []
        self.persona_data = None
        self.resistance_level = None
        self.emotional_state = None
        logger.debug("[AI-decision-layer] Decision layer state has been reset")

    async def make_decision(
        self,
        context: str,
        history: List[dict]
    ) -> Tuple[str, int]:
        """Принимает решение о реакции персонажа.
        
        Args:
            persona_data: Данные персонажа (биография, профиль личности и т.д.)
            context: Текущий контекст/сообщение от терапевта
            resistance_level: Уровень сопротивления ('low', 'medium', 'high')
            emotional_state: Текущее эмоциональное состояние
            history: История диалога в формате списка сообщений
            
        Returns:
            Кортеж (решение, количество использованных токенов)
        """
        tokens_used = 0

        # 1. Формирование промпта для LLM
        prompt = self._build_meta_prompt(
            persona_data=self.persona_data,
            context=context,
            resistance_level=self.resistance_level,
            emotional_state=self.emotional_state,
            history=history
        )
        
        # 2. Получение решения от LLM
        llm_decision, llm_tokens = await self._get_llm_decision(prompt)
        tokens_used += llm_tokens
        
        # 3. Валидация и сохранение решения
        decision = self._validate_and_store_decision(llm_decision)
        
        return decision, tokens_used

    def _validate_and_store_decision(self, decision: str) -> str:
        """Валидирует и сохраняет решение в истории."""
        # Сохраняем решение в истории
        self.recent_decisions.append(decision)
        if len(self.recent_decisions) > self.max_decision_history:
            self.recent_decisions.pop(0)
        
        # Валидация решения
        if decision not in VALID_DECISIONS:
            logger.warning(f"[AI-decision-layer] Invalid LLM decision: {decision}. Falling back to 'respond'")
            return "respond"
            
        return decision
    
    def get_recent_decisions(self, count: Optional[int] = None) -> List[str]:
        """Returns the most recent decisions made by the persona.
        
        Args:
            count: Number of recent decisions to return. If None, returns all.
            
        Returns:
            List of recent decisions in chronological order (newest last).
        """
        if count is None:
            return self.recent_decisions.copy()
        return self.recent_decisions[-count:] if count > 0 else []

    async def _get_llm_decision(self, prompt: str) -> Tuple[str, int]:
        """Получает решение от LLM на основе промпта и логирует обоснование."""
        system_prompt = """
        Ты принимаешь решения для пациента на психотерапии за пациента. Выбери ОДНУ стратегию реакции:

        1. respond — стандартный осмысленный ответ (базовый путь). 70% случаев если нет триггеров, агрессии. но сильно зависит от текущей эмоции и контекста
        2. escalate — эмоциональный, обострённый или агрессивный ответ. 5% случаев, но сильно заависит от текущей эмоции и контекста
        3. self_report — самоанализ, откровенность, честное признание. 5% случаев, но сильно заависит от текущей эмоции и контекста
        4. silence — если нечего сказать, отвечать не хочется, может быть в себя ушел. не используй слишком часто. 5% случаев, но сильно заависит от текущей эмоции и контекста
        5. disengage — завершение общения. 5%, но сильно заависит от текущей эмоции и контекста. если сессия исчерпана или эмоционально перегружен, собеседник агрессивен, груб, незаинтересован - 100%
        6. shift_topic — уход от темы, перевод разговора (например, в случае избегания, стыда, страха), сильно заависит от текущей эмоции и контекста.
        7. open_up — готовность углубиться, признаться, довериться, начать рефлексию (даже если страшно), сильно заависит от текущей эмоции и контекста.

        Руководствуйся:
        - текущим эмоциональным состоянием
        - уровнем сопротивления
        - схемами и защитами
        - историей диалога
        - принятыми ранее решениями, они будут высланы
        - не применяй избегания, молчания, эксалации дольше 2-3 подряд, развивай персонажа. Помни, что персонаж уже пришел на сессию - значит хочет терапевтироваться.
        - всегда уходи если с тобой грубы, агрессивны, холодны, не заинтересованы в том чтобы тебе помочь
        - раскрывайся, если тебя слушают, понимают, действительно пытаются помочь

        Сначала кратко объясни свое решение (1-2 предложения) - мыслями Дмитрия, ведь именно за него ты принимаешь решение. Затем на новой строке напиши только одно слово из списка выше в формате:
        
        [обоснование решения]
        decision: [выбранное_решение]
        """
        
        try:
            response, tokens = await call_llm_for_meta_ai(
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=DECISION_LAYER_TEMP
            )
            
            # Парсим ответ
            if "decision:" in response:
                # Разделяем обоснование и решение
                parts = response.split("decision:")
                reasoning = parts[0].strip()
                decision = parts[1].strip().lower()
                
                # Логируем обоснование
                logger.info(f"[AI-decision-layer] Decision is {decision}, reasoning: {reasoning}, tokens used: {tokens}")
            else:
                decision = response.strip().lower()
                logger.warning(f"[AI-decision-layer] Decision is {decision}, but LLM response doesn't contain reasoning, tokens used: {tokens}")
            
            # Валидация решения
            if decision not in VALID_DECISIONS:
                logger.warning(f"[AI-decision-layer] Invalid LLM decision: {decision}. Falling back to 'respond', tokens used: {tokens}")
                return "respond", tokens
                
            return decision, tokens
            
        except Exception as e:
            logger.error(f"[AI-decision-layer] Error processing LLM decision: {str(e)}", exc_info=True)
            return "respond", 0

    def _build_meta_prompt(
        self,
        persona_data: Dict,
        context: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> str:
        """Строит детализированный промпт для принятия решения."""
        persona = persona_data.get('persona', {})
        
        components = {
            'history': self._format_history(history),
            'symptoms': self._format_symptoms(persona_data),
            'schemas': self._format_list_items(
                persona_data.get('personality_profile', {}).get('predominant_schemas', [])
            ),
            'defenses': self._format_defenses(persona_data),
            'triggers': self._format_list_items(persona_data.get('triggers', [])),
            'decisions': self._format_decision_history()
        }
        
        prompt = f"""
        # Психологический профиль пациента
        Имя: {persona.get('name', 'Неизвестный')}, возраст: {persona.get('age', '?')} лет
        Биография: {persona_data.get('background', 'Нет информации')}
        
        ## Текущее состояние:
        - Эмоциональное: {emotional_state} (триггеры: {components['triggers']})
        - Сопротивление: {resistance_level}
        - Симптомы: {components['symptoms']}
        
        ## Личностные характеристики:
        - Преобладающие схемы: {components['schemas']}
        - Механизмы защиты: {components['defenses']}
        - Стиль привязанности: {self._get_attachment_style(persona_data)}

        ## Последние принятые решения:
        {components['decisions']}
        
        # Контекст сессии:
        История последних сообщений:
        {components['history']}

        Последнее сообщение терапевта:
        "{context}"
        
        # Анализ и решение:
        Учитывая профиль и состояние, как следует реагировать?
        """
        
        logger.debug(f"Built meta prompt for {persona.get('name')}")
        return prompt

    # Вспомогательные методы форматирования (теперь принимают persona_data)
    def _format_history(self, history: List[Dict]) -> str:
        return "\n".join(f"{msg['role']}: {msg['content']}" for msg in history)

    def _format_symptoms(self, persona_data: Dict) -> str:
        symptoms = persona_data.get('current_symptoms', {})
        return "\n".join(f"{k}: {v}" for k, v in symptoms.items()) or "нет явных симптомов"

    def _format_list_items(self, items: List) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "нет данных"

    def _format_defenses(self, persona_data: Dict) -> str:
        defenses = persona_data.get('personality_profile', {}).get('defense_mechanisms', {})
        return "\n".join(f"- {k}: {v}" for k, v in defenses.items()) or "нет данных"

    def _get_attachment_style(self, persona_data: Dict) -> str:
        return persona_data.get('personality_profile', {}).get('attachment_style', 'не определен')

    def _format_decision_history(self) -> str:
        if not self.recent_decisions:
            return "нет данных"
        return "\n".join(f"{i+1}. {d}" for i, d in enumerate(self.recent_decisions))