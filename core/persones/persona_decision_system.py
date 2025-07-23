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
        
        logger.info(f"[AI-decision system] Initialized for {persona_data['persona']['name']}")
    
    async def process_user_message(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, Optional[str], int]:
        """
        Обрабатывает сообщение пользователя и возвращает:
        - принятое решение (respond/escalate/self_report/silence/disengage)
        - подсоленное сообщение (или None для silence/disengage)
        - количество использованных токенов
        """
        state_desc = self._get_human_readable_state(resistance_level, emotional_state)
        logger.info(f"[AI-decision system] Processing message: {user_message[:200]}..., {state_desc}")
        
        # Принимаем мета-решение
        decision, tokens = await self.make_decision(
            user_message,
            resistance_level,
            emotional_state,
            history
        )

        # Обрабатываем решение в зависимости от типа
        if decision == 'disengage':
            base_msg = self._get_disengage_message(emotional_state)
            salted_msg, salt_tokens = await self._salt_disengage_message(
                base_msg,
                user_message,
                resistance_level,
                emotional_state,
                history
            )
            tokens += salt_tokens
            logger.info(f"[AI-decision system] Disengaging with message: {salted_msg}, tokens spent: {tokens}")
            return decision, salted_msg, tokens
        
        elif decision == 'silence':
            logger.info(f"[AI-decision system] Choosing to remain silent, tokens spent: {tokens}")
            return decision, None, tokens
        
        elif decision == 'escalate':
            salted_msg, salt_tokens = await self._salt_message_with_llm(
                user_message,
                'escalate',
                resistance_level,
                emotional_state,
                history
            )
            tokens += salt_tokens
            logger.info(f"[AI-decision system] Escalating with message: {salted_msg},  tokens spent: {tokens}")
            return decision, salted_msg, tokens
        
        elif decision == 'shift_topic':
            salted_msg, salt_tokens = await self._salt_message_with_llm(
                user_message, 'shift_topic', resistance_level, emotional_state, history
            )
            tokens += salt_tokens
            logger.info(f"[AI-decision system] Shifting topic with message: {salted_msg},  tokens spent: {tokens}")
            return decision, salted_msg, tokens

        elif decision == 'open_up':
            salted_msg, salt_tokens = await self._salt_message_with_llm(
                user_message, 'open_up', resistance_level, emotional_state, history
            )
            tokens += salt_tokens
            logger.info(f"[AI-decision system] Opening up with message: {salted_msg},  tokens spent: {tokens}")
            return decision, salted_msg, tokens
        
        elif decision == 'self_report':
            salted_msg, salt_tokens = await self._salt_message_with_llm(
                user_message,
                'self_report',
                resistance_level,
                emotional_state,
                history
            )
            tokens += salt_tokens
            logger.info(f"[AI-decision system] Self-reporting with message: {salted_msg},  tokens spent: {tokens}")
            return decision, salted_msg, tokens
        
        elif decision == 'respond':
            salted_msg, salt_tokens = await self._salt_message_with_llm(
                user_message,
                'respond',
                resistance_level,
                emotional_state,
                history
            )
            tokens += salt_tokens
            logger.info(f"[AI-decision system] Responding with message: {salted_msg}, tokens spent: {tokens}")
            return decision, salted_msg, tokens
    
    def _get_disengage_message(self, emotional_state: str) -> str:
        """Возвращает сообщение для ухода в зависимости от состояния"""
        if emotional_state == 'агрессивный':
            msg = "Я слишком раздражён для этого разговора. Давайте закончим."
        elif emotional_state == 'тревожный и ранимый':
            msg = "Мне нужно побыть одному, я не могу продолжать..."
        elif emotional_state == 'на грани срыва':
            msg = "Я не в состоянии сейчас это обсуждать. Прощайте."
        elif emotional_state == 'в шоке':
            msg = "Мне нужно время чтобы прийти в себя. Завершаем сеанс."
        else:
            msg = "Думаю, нам стоит закончить этот разговор."
        return msg
    
    async def _salt_disengage_message(
        self,
        base_message: str,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Подсаливает сообщение для disengage с учетом контекста"""
        try:
            salt_phrase = await self._generate_salt_phrase(
                strategy="disengage",
                user_message=user_message,
                resistance_level=resistance_level,
                emotional_state=emotional_state,
                history=history
            )
            
            prompt = f"""

            Обязательно учитывай, что ответил терапевт {user_message}.
            
            И историю чата:
            
            {history}

            Если это агрессия - ответь агрессией, можешь сорваться. Действуй в зависимости от эмоционального состояния.
            
            Никогда не выходи из образа пациента
            
            Инструкция для персонализированного завершения:
            *{salt_phrase}*
            
            Учитывай:
            - Текущее эмоциональное состояние: {emotional_state}
            - Уровень сопротивления: {resistance_level}
            - Историю взаимодействия
            """
            
            # Если LLM не смогла сгенерировать подсказку, возвращаем базовое сообщение
            if not salt_phrase.strip():
                return base_message, 0
                
            # Используем LLM для финального оформления сообщения
            system_prompt = f"""
            Ты помогаешь пациенту завершить терапевтическую сессию. 
            Основываясь на базовом сообщении и инструкции, сгенерируй финальную версию.
            Сохрани суть, но сделай более персонализированным и естественным.
            """
            
            final_msg, llm_tokens = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=0.9,
                max_tokens=100
            )
            # Если что-то пошло не так, возвращаем хотя бы базовое сообщение
            if not final_msg.strip():
                return base_message, llm_tokens
            
            return final_msg, llm_tokens + (len(prompt) // 4)
            
        except Exception as e:
            logger.error(f"[AI-decision system] Error salting disengage message: {str(e)}", exc_info=True)
            return base_message, 0

    async def make_decision(
        self,
        context: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Принимает решение о реакции персонажа"""
        state_desc = self._get_human_readable_state(resistance_level, emotional_state)
        
        cache_key = self._create_cache_key(context, resistance_level, emotional_state)
        if cache_key in self.decision_cache:
            logger.debug(f"Cache hit for key: {cache_key}")
            return self.decision_cache[cache_key], 0
        
        tokens_used = 0

        prompt = self._build_meta_prompt(context, resistance_level, emotional_state, history)
        llm_decision, llm_tokens = await self._get_llm_decision(prompt)
        logger.info(f"[AI-decision system] LLM desicion: {llm_decision}, tokens spent {llm_tokens}")
        tokens_used += llm_tokens

        if not hasattr(self, 'recent_decisions'):
            self.recent_decisions = []
        self.recent_decisions.append(llm_decision)
        if len(self.recent_decisions) > 5:
            self.recent_decisions.pop(0)
        
        if llm_decision in ('respond', 'escalate', 'self_report', 'silence', 'disengage', 'shift_topic', 'open_up'):
            self.decision_cache[cache_key] = llm_decision
            logger.info(f"LLM decision: {llm_decision} for {state_desc}")
            return llm_decision, tokens_used
        else:
            logger.warning(f"[AI-decision system] Invalid LLM decision: {llm_decision}. Falling back to default 'respond'")
        
        # Фолбэк решение, если LLM не используется или вернул недопустимое значение
        decision = 'respond'
        self.decision_cache[cache_key] = decision
        
        logger.info(f"Fallback decision: {decision} for {state_desc}")
        return decision, tokens_used

    def _get_human_readable_state(self, resistance: str, emotion: str) -> str:
        """Возвращает человекочитаемое описание состояния"""
        return f"Сопротивление: {resistance}, эмоция: {emotion}"

    def _create_cache_key(self, context: str, resistance: str, emotion: str) -> str:
        """Создает ключ для кэширования решений"""
        return f"{context[:50]}_{resistance}_{emotion}"

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 150
    ) -> Tuple[str, int]:
        """
        Универсальный метод для запросов к LLM
        Возвращает:
        - ответ LLM
        - количество использованных токенов
        """
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response, tokens = await get_response(
                messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            logger.debug(f"[AI-decision system] LLM response: {response[:200]}... (tokens: {tokens})")
            return response.strip(), tokens
            
        except Exception as e:
            logger.error(f"[AI-decision system] LLM call error: {str(e)}", exc_info=True)
            return "", 0

    async def _generate_salt_phrase(
        self,
        strategy: str,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> str:
        """Генерирует контекстно-зависимую фразу для подсолки через LLM"""
        history_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history[-3:]
        )
        
        persona = self.persona_data.get('persona', {})
        profile = self.persona_data.get('personality_profile', {})
        
        system_prompt = f"""
        Ты психологический ассистент, помогающий формировать естественные ответы пациента в терапии.
        Сгенерируй краткую (1-2 предложения), конкретную инструкцию для ответа пациента.
        
        Информация о пациенте:
        Имя: {persona.get('name', 'Неизвестный')}
        Возраст: {persona.get('age', '?')}
        Стиль привязанности: {profile.get('attachment_style', 'не определен')}
        Преобладающие схемы: {', '.join(profile.get('predominant_schemas', [])) if profile.get('predominant_schemas') else 'нет данных'}

        """
        
        tone_data = self.persona_data.get("tone", {})
        defenses = profile.get("defense_mechanisms", {})
        last_decisions = "\n".join(f"{i+1}. {d}" for i, d in enumerate(self.recent_decisions)) if hasattr(self, 'recent_decisions') else "нет данных"

        user_prompt = f"""
        Контекст:
        - Стратегия ответа: {strategy}
        - Текущее сопротивление: {resistance_level}
        - Эмоциональное состояние: {emotional_state}
        - Механизмы защиты: {', '.join(defenses.keys()) if defenses else 'не определены'}
        
        Стиль общения:
        - Базовый: {tone_data.get("baseline", "—")}
        - При защите: {tone_data.get("defensive_reaction", "—")}
        
        1. respond — стандартный ответ
        2. escalate — эмоциональная реакция
        3. self_report — самоанализ
        4. silence — пауза
        5. disengage — завершение
        6. shift_topic — перевод темы
        7. open_up — углубление в терапию

        Учитывай, что shift_topic — это защитная стратегия (избегание), а open_up — признак доверия и снижения сопротивления.

        Хронология решений: 
        {last_decisions}

        
        Про персонажа:
        - Поведенческие правила: {', '.join(self.persona_data.get('behaviour_rules', [])) if self.persona_data.get('behaviour_rules') else 'нет'}
        - Типичные самоотчеты: {', '.join(self.persona_data.get('self_reports', [])) if self.persona_data.get('self_reports') else 'нет'}
        - Триггеры: {', '.join(self.persona_data.get('triggers', [])) if self.persona_data.get('triggers') else 'нет'}
        
        # Внимание: в исторической переписке:
        ##         - ASSISTANT - это пациент (персонаж, которому ты ассистируешь)
        ##         - USER - это терапевт (собеседник пациента)

        История последних сообщений:
        {history_text}
        
        Новое сообщение терапевта:
        "{user_message}"
        
        Сгенерируй только саму инструкцию для пациента, без пояснений.
        Учитывай особенности персонажа, его защитные механизмы и текущее состояние.
        ВАЖНО: не давай четкую фразу для ответа, напиши инструкцию так, чтобы пациент сам придумал ответ и терапия развивалась или не развивалась в зависимости от профессинализма терапевта.
        """
        
        response, _ = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.9  # Более креативные ответы, чем у персоны (0.8)
        )
        
        return response

    async def _get_llm_decision(self, prompt: str) -> Tuple[str, int]:
        """Получает решение от мета нейросети, принимающей решения"""
        system_prompt = """
        Ты принимаешь решения для пациента на психотерапии. Выбери ОДНУ стратегию реакции:

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

        Выбери только **одно** слово из списка выше.
        """
        decision, tokens = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=1.2  # Низкая температура для более предсказуемых решений
        )
        
        if decision not in ('respond', 'escalate', 'self_report', 'silence', 'disengage', 'shift_topic', 'open_up'):
            logger.warning(f"[AI-decision system] Invalid LLM decision: {decision}")
            return "respond", tokens
            
        return decision, tokens

    def _build_meta_prompt(
        self,
        context: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> str:
        """Строит промпт для мета-решения с расширенной психологической информацией"""
        persona = self.persona_data.get('persona', {})
        background = self.persona_data.get('background', 'Нет информации о биографии')
        profile = self.persona_data.get('personality_profile', {})
        
        resistance = res_map.get(resistance_level, resistance_level)
        emotion = emo_map.get(emotional_state, emotional_state)
        
        history_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history
        )
        
        # Форматирование ключевых психологических характеристик
        def format_items(items):
            return "\n".join(f"- {item}" for item in items) if items else "нет данных"
            
        current_symptoms = "\n".join(f"{k}: {v}" for k,v in self.persona_data.get('current_symptoms', {}).items())
        schemas = format_items(profile.get('predominant_schemas', []))
        defenses = "\n".join(f"- {k}: {v}" for k,v in profile.get('defense_mechanisms', {}).items())
        triggers = format_items(self.persona_data.get('triggers', []))
        last_decisions = "\n".join(f"{i+1}. {d}" for i, d in enumerate(self.recent_decisions)) if hasattr(self, 'recent_decisions') else "нет данных"
        prompt = f"""
        # Психологический профиль пациента
        Имя: {persona.get('name', 'Неизвестный')}, возраст: {persona.get('age', '?')} лет
        Биография: {background}
        
        ## Текущее состояние:
        - Эмоциональное: {emotion} (триггеры: {triggers})
        - Сопротивление: {resistance}
        - Симптомы: {current_symptoms or 'нет явных симптомов'}
        
        ## Личностные характеристики:
        - Преобладающие схемы: {schemas}
        - Механизмы защиты: {defenses}
        - Стиль привязанности: {profile.get('attachment_style', 'не определен')}

        ## ВАЖНО, твои последние принятые решения персонажа:
        {last_decisions}
        
        # Доступные стратегии:
        1. respond — стандартный ответ
        2. escalate — эмоциональная реакция
        3. self_report — самоанализ
        4. silence — пауза
        5. disengage — завершение
        6. shift_topic — перевод темы
        7. open_up — углубление в терапию
        
        # Контекст сессии ( ты "assistant" - пациент, "user" - психотерапевт
        История последних сообщений:
        {history_text}

        #
        Последнее сообщение терапевта:
        "{context}"
        
        # Анализ и решение
        Учитывая психологический профиль, текущее состояние и историю взаимодействия, как следует реагировать?

        
        
        Выбери ОДНУ стратегию, наиболее соответствующую:
        - текущему эмоциональному состоянию ({emotion})
        - уровню сопротивления ({resistance})
        - задействованным схемам ({schemas})
        - активированным защитным механизмам ({defenses})
        - истории взаимодействия
        """
        
        logger.debug(f"[AI-decision system] Built enhanced meta prompt:\n{prompt}...")
        return prompt
    
    # поведенческая инерция — снижать вероятность повторения одной и той же стратегии несколько раз подряд:
    # нужно более сложно сделать на основе реакций
        
    async def _salt_message_with_llm(
        self,
        user_message: str,
        strategy: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        try:
            last_decisions = "\n".join(f"{i+1}. {d}" for i, d in enumerate(self.recent_decisions)) if hasattr(self, 'recent_decisions') else "нет данных"
            salt_phrase = await self._generate_salt_phrase(
                strategy=strategy,
                user_message=user_message,
                resistance_level=resistance_level,
                emotional_state=emotional_state,
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
            logger.info(f"[AI-decision system] Salted message (dynamic basic): {prompt[:100]}...")
            return prompt, tokens
            
        except Exception as e:
            logger.error(f"[AI-decision system] Error in _salt_user_message: {str(e)}", exc_info=True)
            return user_message, 0