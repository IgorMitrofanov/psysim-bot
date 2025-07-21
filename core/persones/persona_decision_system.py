import random
from typing import List, Dict, Tuple, Optional
from core.persones.llm_engine import get_response
from config import logger

# Маппинги для человекочитаемых описаний
res_map = {
    "resistance_medium": "средний",
    "resistance_high": "высокий",
    "resistance_low": "низкий"
}

emo_map = {
    "emotion_anxious": "тревожный и ранимый",
    "emotion_aggressive": "агрессивный",
    "emotion_cold": "холодный и отстранённый",
    "emotion_shocked": "в шоке",
    "emotion_breakdown": "на грани срыва",
    "emotion_superficial": "поверхностно весёлый",
    "emotion_neutral": "нейтральный",
    "emotion_depressed": "подавленный"
}

class PersonaDecisionSystem:
    def __init__(self, persona_data: Dict):
        self.persona_data = persona_data
        self.decision_cache = {}
        
        # Базовые вероятности решений
        self.base_probabilities = {
            'respond': 0.5,
            'escalate': 0.15,
            'self_report': 0.1,
            'silence': 0.2,
            'disengage': 0.05
        }
        
        # Модификаторы для разных эмоциональных состояний
        self.emotion_modifiers = {
            'emotion_anxious': {
                'respond': -0.1,
                'escalate': -0.2,
                'self_report': +0.3,
                'silence': +0.2,
                'disengage': +0.1
            },
            'emotion_aggressive': {
                'respond': +0.1,
                'escalate': +0.3,
                'self_report': -0.2,
                'silence': -0.1,
                'disengage': +0.1
            },
            'emotion_cold': {
                'respond': -0.2,
                'escalate': -0.1,
                'self_report': -0.1,
                'silence': +0.3,
                'disengage': +0.1
            },
            'emotion_shocked': {
                'respond': -0.3,
                'escalate': +0.1,
                'self_report': +0.2,
                'silence': +0.3,
                'disengage': +0.2
            },
            'emotion_breakdown': {
                'respond': -0.4,
                'escalate': +0.4,
                'self_report': +0.2,
                'silence': +0.1,
                'disengage': +0.3
            },
            'emotion_superficial': {
                'respond': +0.2,
                'escalate': -0.3,
                'self_report': -0.2,
                'silence': -0.1,
                'disengage': -0.1
            },
            'emotion_neutral': {},
            'emotion_depressed': {
                'respond': -0.1,
                'escalate': -0.2,
                'self_report': +0.3,
                'silence': +0.2,
                'disengage': +0.1
            }
        }
        
        # Модификаторы для разных уровней сопротивления
        self.resistance_modifiers = {
            'resistance_high': {
                'respond': -0.2,
                'escalate': +0.3,
                'self_report': -0.1,
                'silence': +0.2,
                'disengage': +0.2
            },
            'resistance_medium': {},
            'resistance_low': {
                'respond': +0.2,
                'escalate': -0.1,
                'self_report': +0.1,
                'silence': -0.1,
                'disengage': -0.1
            }
        }
        
        logger.info(f"Initialized PersonaDecisionSystem for {persona_data['persona']['name']}")

    async def process_user_message(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict],
        use_llm: bool = True
    ) -> Tuple[str, Optional[str], int]:
        """
        Обрабатывает сообщение пользователя и возвращает:
        - принятое решение (respond/escalate/self_report/silence/disengage)
        - подсоленное сообщение (или None для silence/disengage)
        - количество использованных токенов
        """
        state_desc = self._get_human_readable_state(resistance_level, emotional_state)
        logger.info(f"Processing message: {user_message[:100]}..., {state_desc}")
        
        # Принимаем мета-решение
        decision, tokens = await self.make_decision(
            user_message,
            resistance_level,
            emotional_state,
            history,
            use_llm
        )
        
        # Обрабатываем решение
        if decision == 'disengage':
            msg = self._get_disengage_message(emotional_state)
            logger.info(f"Disengaging with message: {msg}")
            return decision, msg, tokens
        
        if decision == 'silence':
            logger.info("Choosing to remain silent")
            return decision, None, tokens
        
        # Подсаливаем сообщение в зависимости от типа решения
        salted_msg, salt_tokens = await self._salt_message(
            decision,
            user_message,
            resistance_level,
            emotional_state,
            history
        )
        tokens += salt_tokens
        
        return decision, salted_msg, tokens

    async def _salt_message(
        self,
        decision_type: str,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[Optional[str], int]:
        """Подсаливает сообщение в зависимости от типа решения"""
        try:
            if decision_type == 'escalate':
                return await self._salt_with_escalation(user_message, resistance_level, emotional_state, history)
            elif decision_type == 'self_report':
                return await self._salt_with_self_report(user_message, resistance_level, emotional_state, history)
            else:  # respond
                return await self._salt_user_message(user_message, resistance_level, emotional_state, history)
        except Exception as e:
            logger.error(f"Error salting message: {str(e)}", exc_info=True)
            return user_message, 0

    async def make_decision(
        self,
        context: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict],
        use_llm: bool = True
    ) -> Tuple[str, int]:
        """Принимает решение о реакции персонажа"""
        state_desc = self._get_human_readable_state(resistance_level, emotional_state)
        logger.debug(f"Making decision for context: {context[:50]}..., {state_desc}")
        
        cache_key = self._create_cache_key(context, resistance_level, emotional_state)
        if cache_key in self.decision_cache:
            logger.debug(f"Cache hit for key: {cache_key}")
            return self.decision_cache[cache_key], 0
        
        tokens_used = 0
        
        if use_llm:
            prompt = self._build_meta_prompt(context, resistance_level, emotional_state, history)
            llm_decision, llm_tokens = await self._get_llm_decision(prompt)
            tokens_used += llm_tokens
            
            if llm_decision in ('respond', 'escalate', 'self_report', 'silence', 'disengage'):
                self.decision_cache[cache_key] = llm_decision
                logger.info(f"LLM decision: {llm_decision} for {state_desc}")
                return llm_decision, tokens_used
            else:
                logger.warning(f"Invalid LLM decision: {llm_decision}. Falling back to probabilistic")
        
        decision = self._get_probabilistic_decision(resistance_level, emotional_state)
        self.decision_cache[cache_key] = decision
        
        logger.info(f"Probabilistic decision: {decision} for {state_desc}")
        return decision, tokens_used

    def _get_human_readable_state(self, resistance: str, emotion: str) -> str:
        """Возвращает человекочитаемое описание состояния"""
        return f"Сопротивление: {resistance}, эмоция: {emotion}"

    def _create_cache_key(self, context: str, resistance: str, emotion: str) -> str:
        """Создает ключ для кэширования решений"""
        return f"{context[:50]}_{resistance}_{emotion}"

    async def _get_llm_decision(self, prompt: str) -> Tuple[str, int]:
        """Получает решение от LLM"""
        try:
            messages = [
                {"role": "system", "content": "Выбери только одно слово (respond/escalate/self_report/silence/disengage)"},
                {"role": "user", "content": prompt}
            ]
            
            response, tokens = await get_response(messages, temperature=0.3)
            decision = response.strip().lower()
            
            if decision in ('respond', 'escalate', 'self_report', 'silence', 'disengage'):
                logger.debug(f"Received valid LLM decision: {decision}")
                return decision, tokens
                
            logger.warning(f"Invalid LLM decision received: {decision}")
            raise ValueError(f"Invalid decision: {decision}")
            
        except Exception as e:
            logger.error(f"LLM decision error: {str(e)}", exc_info=True)
            return None, tokens if 'tokens' in locals() else 0

    def _get_probabilistic_decision(
        self,
        resistance_level: str,
        emotional_state: str
    ) -> str:
        """Принимает решение на основе вероятностей с модификаторами"""
        probs = self.base_probabilities.copy()
        
        # Применяем модификаторы эмоций
        emotion_mod = self.emotion_modifiers.get(emotional_state, {})
        for k, v in emotion_mod.items():
            probs[k] = max(0, min(1, probs[k] + v))
        
        # Применяем модификаторы сопротивления
        resistance_mod = self.resistance_modifiers.get(resistance_level, {})
        for k, v in resistance_mod.items():
            probs[k] = max(0, min(1, probs[k] + v))
        
        # Нормализуем вероятности
        total = sum(probs.values())
        if total == 0:
            logger.error("All probabilities zero after modifiers!")
            return 'respond'
            
        normalized = {k: v/total for k, v in probs.items()}
        
        logger.debug(
            f"Decision probabilities for {emotional_state}/{resistance_level}:\n"
            f"Base: {self.base_probabilities}\n"
            f"Modified: {normalized}"
        )
        
        # Выбираем решение
        rand = random.random()
        cumulative = 0
        for decision, prob in normalized.items():
            cumulative += prob
            if rand < cumulative:
                logger.debug(f"Selected decision: {decision} (random value: {rand:.3f})")
                return decision
        
        logger.error("Probability selection failed, fallback to 'respond'")
        return 'respond'

    def _build_meta_prompt(
        self,
        context: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> str:
        """Строит промпт для мета-решения"""
        persona = self.persona_data.get('persona', {})
        background = self.persona_data.get('background', 'Нет информации о биографии')
        
        resistance = res_map.get(resistance_level, resistance_level)
        emotion = emo_map.get(emotional_state, emotional_state)
        
        history_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history[-3:]
        )
        
        prompt = f"""
        Ты {persona.get('name', 'Неизвестный')}, {persona.get('age', '?')} лет. {background}
        Текущее состояние: {emotion}, сопротивление: {resistance}
        
        История:
        {history_text}
        
        Последнее сообщение:
        {context}
        
        Как реагировать? Выбери ОДНО:
        - respond (обычный ответ)
        - escalate (эмоционально усиленный ответ)
        - self_report (ответ с самоанализом)
        - silence (игнорировать)
        - disengage (завершить сеанс)
        """
        
        logger.debug(f"Built meta prompt:\n{prompt[:200]}...")
        return prompt

    def _get_disengage_message(self, emotional_state: str) -> str:
        """Возвращает сообщение для ухода в зависимости от состояния"""
        if emotional_state == 'emotion_aggressive':
            msg = "Я слишком раздражён для этого разговора. Давайте закончим."
        elif emotional_state == 'emotion_anxious':
            msg = "Мне нужно побыть одному, я не могу продолжать..."
        elif emotional_state == 'emotion_breakdown':
            msg = "Я не в состоянии сейчас это обсуждать. Прощайте."
        elif emotional_state == 'emotion_shocked':
            msg = "Мне нужно время чтобы прийти в себя. Завершаем сеанс."
        else:
            msg = "Думаю, нам стоит закончить этот разговор."
        
        logger.debug(f"Disengage message for {emotional_state}: {msg}")
        return msg

    async def _salt_user_message(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Добавляет базовую 'соль' к сообщению пользователя"""
        try:
            prompt = f"""
            Терапевт пишет
            "{user_message}"
            
            *Отвечай за собеседника*
            """
            
            tokens = len(prompt) // 4 
            logger.debug(f"Salted message (basic): {prompt[:100]}...")
            return prompt, tokens
        except Exception as e:
            logger.error(f"Error in _salt_user_message: {str(e)}", exc_info=True)
            return user_message, 0

    async def _salt_with_escalation(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Добавляет эскалацию к сообщению"""
        try:
            prompt = f"""
            Терапевт пишет:
            "{user_message}"
            
            *Добавь эмоциональной эскалации в ответ на сообщение от теапевта, усиливая его эмоциональную окраску*
            """
            
            tokens = len(prompt) // 4 
            
            logger.debug(f"Salted message (escalated): {prompt[:100]}...")
            return prompt, tokens
        except Exception as e:
            logger.error(f"Error in _salt_with_escalation: {str(e)}", exc_info=True)
            return user_message, 0

    async def _salt_with_self_report(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Добавляет самоанализ к сообщению"""
        try:
            prompt = f"""
            Терапевт пишет:
            "{user_message}"
            
            *Сначала кратко ответь на сообщение, затем добавь анализ своих эмоций и состояния.*
            """
            
            tokens = len(prompt) // 4 
            
            logger.debug(f"Salted message (self-report): {prompt[:100]}...")
            return prompt, tokens
        except Exception as e:
            logger.error(f"Error in _salt_with_self_report: {str(e)}", exc_info=True)
            return user_message, 0