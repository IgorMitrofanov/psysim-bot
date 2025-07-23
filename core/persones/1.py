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
        
        logger.info(f"Initialized PersonaDecisionSystem for {persona_data['persona']['name']}")

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
        logger.info(f"Processing message: {user_message[:100]}..., {state_desc}")
        
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
            logger.info(f"Disengaging with message: {salted_msg}")
            return decision, salted_msg, tokens
        
        elif decision == 'silence':
            logger.info("Choosing to remain silent")
            return decision, None, tokens
        
        elif decision == 'escalate':
            salted_msg, salt_tokens = await self._salt_with_escalation(
                user_message,
                resistance_level,
                emotional_state,
                history
            )
            tokens += salt_tokens
            logger.info(f"Escalating with message: {salted_msg}")
            return decision, salted_msg, tokens
        
        elif decision == 'self_report':
            salted_msg, salt_tokens = await self._salt_with_self_report(
                user_message,
                resistance_level,
                emotional_state,
                history
            )
            tokens += salt_tokens
            logger.info(f"Self-reporting with message: {salted_msg}")
            return decision, salted_msg, tokens
        
        elif decision == 'respond':
            salted_msg, salt_tokens = await self._salt_user_message(
                user_message,
                resistance_level,
                emotional_state,
                history
            )
            tokens += salt_tokens
            logger.info(f"Responding with message: {salted_msg}")
            return decision, salted_msg, tokens
        
        else:
            logger.warning(f"Unknown decision type: {decision}. Falling back to default respond")
            salted_msg, salt_tokens = await self._salt_user_message(
                user_message,
                resistance_level,
                emotional_state,
                history
            )
            tokens += salt_tokens
            return 'respond', salted_msg, tokens
    
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
        
        logger.debug(f"Disengage message for {emotional_state}: {msg}")
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
            Базовое сообщение для завершения:
            "{base_message}"
            
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

                
            return prompt, (len(prompt) // 4)
            
        except Exception as e:
            logger.error(f"Error salting disengage message: {str(e)}", exc_info=True)
            return base_message, 0

    async def _salt_message_generic(
        self,
        base_message: Optional[str],
        strategy: str,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict],
        additional_instructions: str = ""
    ) -> Tuple[str, int]:
        """
        Универсальная функция для подсаливания сообщений любого типа.
        
        Параметры:
        - base_message: базовое сообщение (может быть None)
        - strategy: тип стратегии (basic, escalate, self_report, disengage)
        - user_message: сообщение пользователя
        - resistance_level: уровень сопротивления
        - emotional_state: эмоциональное состояние
        - history: история диалога
        - additional_instructions: дополнительные инструкции для LLM
        
        Возвращает:
        - подсоленное сообщение
        - количество использованных токенов
        """
        try:
            # Генерируем инструкцию для подсаливания
            salt_phrase = await self._generate_salt_phrase(
                strategy=strategy,
                user_message=user_message,
                resistance_level=resistance_level,
                emotional_state=emotional_state,
                history=history
            )
            
            # Если не получили инструкцию, возвращаем базовое сообщение или оригинальное
            if not salt_phrase.strip():
                return base_message or user_message, 0
                
            # Формируем промпт для LLM
            prompt_parts = []
            if base_message:
                prompt_parts.append(f"Базовое сообщение:\n\"{base_message}\"")
            
            prompt_parts.append(f"Сообщение терапевта:\n\"{user_message}\"")
            prompt_parts.append(f"Инструкция для ответа:\n*{salt_phrase}*")
            
            if additional_instructions:
                prompt_parts.append(f"Дополнительные указания:\n{additional_instructions}")
                
            prompt = "\n\n".join(prompt_parts)
            
                
            return prompt, (len(prompt) // 4)
            
        except Exception as e:
            logger.error(f"Error in _salt_message_generic: {str(e)}", exc_info=True)
            return base_message or user_message, 0
    
    async def make_decision(
        self,
        context: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Принимает решение о реакции персонажа"""
        state_desc = self._get_human_readable_state(resistance_level, emotional_state)
        logger.debug(f"Making decision for context: {context[:50]}..., {state_desc}")
        
        cache_key = self._create_cache_key(context, resistance_level, emotional_state)
        if cache_key in self.decision_cache:
            logger.debug(f"Cache hit for key: {cache_key}")
            return self.decision_cache[cache_key], 0
        
        tokens_used = 0
        

        prompt = self._build_meta_prompt(context, resistance_level, emotional_state, history)
        llm_decision, llm_tokens = await self._get_llm_decision(prompt)
        tokens_used += llm_tokens
        
        if llm_decision in ('respond', 'escalate', 'self_report', 'silence', 'disengage'):
            self.decision_cache[cache_key] = llm_decision
            logger.info(f"LLM decision: {llm_decision} for {state_desc}")
            return llm_decision, tokens_used
        else:
            logger.warning(f"Invalid LLM decision: {llm_decision}. Falling back to default 'respond'")
        
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
            
            logger.debug(f"LLM response: {response[:200]}... (tokens: {tokens})")
            return response.strip(), tokens
            
        except Exception as e:
            logger.error(f"LLM call error: {str(e)}", exc_info=True)
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
        
        user_prompt = f"""
        Контекст:
        - Стратегия ответа: {strategy}
        - Текущее сопротивление: {resistance_level}
        - Эмоциональное состояние: {emotional_state}
        - Механизмы защиты: {', '.join(defenses.keys()) if defenses else 'не определены'}
        
        Стиль общения:
        - Базовый: {tone_data.get("baseline", "—")}
        - При защите: {tone_data.get("defensive_reaction", "—")}
        
        Доступные стратегии:
        1. respond (стандартный ответ) - если диалог идет нормально
        2. escalate (эмоциональная реакция) - если затронуты триггеры или сопротивление растет
        3. self_report (самоанализ) - если терапевт запрашивает рефлексию или есть возможность раскрыться
        4. silence (пауза) - проверка реакции терапевта, или при эмоциях, избегай без веской причины
        5. disengage (завершение) - если сессия исчерпана или эмоционально перегружен, собеседник агрессивен, груб, незаинтересован. не уходи сразу после приветствия, дай шанс
        
        
        Про персонажа:
        - Поведенческие правила: {', '.join(self.persona_data.get('behaviour_rules', [])) if self.persona_data.get('behaviour_rules') else 'нет'}
        - Типичные самоотчеты: {', '.join(self.persona_data.get('self_reports', [])) if self.persona_data.get('self_reports') else 'нет'}
        - Триггеры: {', '.join(self.persona_data.get('triggers', [])) if self.persona_data.get('triggers') else 'нет'}
        
        Внимание: в исторической переписке:
        - ASSISTANT - это пациент (персонаж, которого мы изображаем)
        - USER - это терапевт (собеседник пациента)
        
        История последних сообщений:
        {history_text}
        
        Новое сообщение терапевта:
        "{user_message}"
        
        Сгенерируй только саму **инструкцию** для пациента, без пояснений. Это важно, не реплику - а инструкцию, как эту реплику сделать.
        Учитывай особенности персонажа, его защитные механизмы и текущее состояние.
        
        Примеры хороших инструкций:
        - "Ответь с долей скепсиса, но раскрой одну деталь из прошлого"
        - "Эмоционально отреагируй на предполагаемый подтекст вопроса"
        - "Сначала кратко ответь на вопрос, затем добавь рефлексию о своих чувствах"
        - "Используй юмор для дистанцирования, как обычно делаешь в напряженных ситуациях"
        """
        
        response, _ = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.  # Более детерминированные ответы
        )
        
        return response

    async def _get_llm_decision(self, prompt: str) -> Tuple[str, int]:
        """Получает решение от LLM с использованием универсального метода"""
        system_prompt = """
        Ты принимаешь решения для пациента на психотерапии. Выбери ОДНУ стратегию реакции:
        - respond: обычный ответ. Использоваться для развития персонажа
        - escalate: эмоционально усиленный ответ. Не используй слишком часто
        - self_report: ответ с самоанализом
        - silence: игнорировать сообщение
        - disengage: завершить сеанс
        
        Верни только одно слово (без пояснений) из списка выше.
        """
        
        decision, tokens = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=0.4  
        )
        
        if decision not in ('respond', 'escalate', 'self_report', 'silence', 'disengage'):
            logger.warning(f"Invalid LLM decision: {decision}")
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
            f"{msg['role']}: {msg['content']}" for msg in history[-3:]
        )
        
        # Форматирование ключевых психологических характеристик
        def format_items(items):
            return "\n".join(f"- {item}" for item in items) if items else "нет данных"
        
        def format_list(items):
            return "\n".join(f"- {item}" for item in items) if items else "—"
    
        self_reports_text = format_list(self.persona_data.get("self_reports", []))
        escalation_text = format_list(self.persona_data.get("escalation", []))
        current_symptoms = "\n".join(f"{k}: {v}" for k,v in self.persona_data.get('current_symptoms', {}).items())
        schemas = format_items(profile.get('predominant_schemas', []))
        defenses = "\n".join(f"- {k}: {v}" for k,v in profile.get('defense_mechanisms', {}).items())
        triggers = format_items(self.persona_data.get('triggers', []))
        rules_text = format_list(self.persona_data.get("behaviour_rules", []))
        
        tone_data = self.persona_data.get("tone", {})
        tone_text = f"""
        - базовый стиль:  
        { tone_data.get("baseline", "—")}
        - защитные реакции:
        {tone_data.get("defensive_reaction", "—")}
        """
        
        prompt = f"""
        # Психологический профиль пациента
        Имя: {persona.get('name', 'Неизвестный')}, возраст: {persona.get('age', '?')} лет
        Биография: {background}
        
        ВАЖНО: При проявлении агрессии в сообщениях терапевта, не желание вам помочь, отстаренности -> disengage
        
        ## Текущее состояние:
        - Эмоциональное: {emotion} (триггеры: {triggers})
        - Сопротивление: {resistance}
        - Симптомы: {current_symptoms or 'нет явных симптомов'}
        
        ## Личностные характеристики:
        - Преобладающие схемы: {schemas}
        - Механизмы защиты: {defenses}
        - Стиль привязанности: {profile.get('attachment_style', 'не определен')}
        
        # Контекст сессии
        История последних сообщений (макс. 3):
        {history_text}
        
        Учитывай контекст диалога, старайся не повторяться и разиваться (смотреть историю сообщений - ты "assistant" - пациент, "user" - психотерапевт)
        
        
        Последнее сообщение терапевта:
        "{context}"
        
        # Анализ и решение
        Учитывая психологический профиль, текущее состояние и историю взаимодействия, как следует реагировать?
        
        Доступные стратегии:
        1. respond (стандартный ответ) - если диалог идет нормально, развивается терапия
        2. escalate (эмоциональная реакция) - если затронуты триггеры или сопротивление растет. ниже есть база
        3. self_report (самоанализ) - если терапевт запрашивает рефлексию или есть возможность раскрыться. ниже есть база
        4. silence (пауза) - нечего ответить, шок, потрясение, издевательно, сарказм
        5. disengage (завершение) - если сессия исчерпана или эмоционально перегружен, собеседник агрессивен, отстраен, не желает вам помочь, не понимает
        
        # база самоотчёты
        {self_reports_text}    

        # база эскалация  
        {escalation_text}   
        
        # манера общения  
        {tone_text}
        
        # поведенческие правила  
        {rules_text}
        
        Выбери ОДНУ стратегию, наиболее соответствующую:
        - текущему эмоциональному состоянию ({emotion})
        - уровню сопротивления ({resistance})
        - задействованным схемам ({schemas})
        - активированным защитным механизмам ({defenses})
        - истории взаимодействия
        """
        
        logger.debug(f"Built enhanced meta prompt:\n{prompt}...")
        return prompt

    async def _salt_user_message(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Подсаливание стандартного ответа с динамическими инструкциями по развитию персонажа"""
        # Генерируем дополнительные инструкции по развитию персонажа
        dynamic_instructions, inst_tokens = await self._generate_character_development_instructions(
            user_message,
            resistance_level,
            emotional_state,
            history
        )
        
        additional_instructions = f"""
        Основные указания:
        - Отвечай в роли своего персонажа, не выходи из образа. Ты - пациент.
        - Используй характерные для персонажа речевые паттерны и манеру общения
        
        Выбери что-то одно для создания ответа терапевту от пациента. Твой ответ должн выглядеть как инструкция для ответа терапевту.
        {dynamic_instructions}
        
        Техники терапевтического взаимодействия:
        - Постепенно раскрывай новые детали своей биографии
        - Связывай текущие реакции с прошлым опытом
        - Проявляй характерные для персонажа защитные механизмы естественным образом
        """
        
        result = await self._salt_message_generic(
            base_message=None,
            strategy="basic",
            user_message=user_message,
            resistance_level=resistance_level,
            emotional_state=emotional_state,
            history=history,
            additional_instructions=additional_instructions
        )
        
        # Суммируем токены (из генерации инструкций + основного запроса)
        return result[0], result[1] + inst_tokens

    async def _generate_character_development_instructions(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Генерирует динамические инструкции для развития персонажа на основе истории"""
        system_prompt = """
        Ты психологический ассистент, помогающий сформулировать указания для развития персонажа пациента.
        Проанализируй историю диалога и предложи:
        1. Какие аспекты биографии стоит раскрыть в ответе
        2. Какие темы из истории стоит развить
        3. Какие защитные механизмы естественно проявить
        4. Какие элементы из прошлого опыта можно связать с текущей ситуацией
        
        Сформулируй 3-4 конкретных указания для естественного развития персонажа. Предупреди, что слишком развернутый ответ не нужен.
        """
        
        history_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history[-4:]
        )
        
        user_prompt = f"""
        Контекст персонажа:
        - Уровень сопротивления: {resistance_level}
        - Эмоциональное состояние: {emotional_state}
        - Ключевые моменты биографии: {', '.join(self.persona_data.get('biography', {}).get('key_points', [])) if self.persona_data.get('biography', {}).get('key_points') else 'нет данных'}
        - Неисследованные темы: {', '.join(self.persona_data.get('unexplored_topics', [])) if self.persona_data.get('unexplored_topics') else 'нет данных'}
        
        
        Предупреди, что слишком развернутый ответ не нужен.
        Предупредить отвечать в контексте истории сообщений, и не выходить из образа. (смотреть историю сообщений - ты "assistant" - пациент, "user" - психотерапевт)
        
        
        История диалога:
        {history_text}
        
        Последнее сообщение терапевта:
        "{user_message}"
        
        Сгенерируй 3-4 конкретных указания для развития персонажа, например:
        - "Упомяни случай из подросткового возраста, связанный с текущей темой"
        - "Прояви характерное для персонажа избегание через изменение темы"
        - "Раскрой новый аспект отношений с матерью, который ранее не обсуждался"
        - "Свяжи текущую реакцию с травматическим опытом из прошлого"
        """
        
        response, tokens = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.5,
            max_tokens=150
        )
        
        return response.strip(), tokens

    async def _salt_with_self_report(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Подсаливание ответа с самоанализом с динамически генерируемыми инструкциями"""
        # Генерируем дополнительные инструкции на основе истории
        dynamic_instructions, inst_tokens = await self._generate_self_report_instructions(
            user_message,
            resistance_level,
            emotional_state,
            history
        )
        
        additional_instructions = f"""
        Выбери что-то одно для создания ответа терапевту от пациента. Твой ответ должн выглядеть как инструкция для ответа терапевту.
        
        История сообщений:
        {history}
        
        Предупреди, что слишком развернутый ответ не нужен.
        Предупредить отвечать в контексте истории сообщений, и не выходить из образа. (смотреть историю сообщений - ты "assistant" - пациент, "user" - психотерапевт)

        
        Динамические указания:
        {dynamic_instructions}
        
        Важно:
        - Не забывай, ты в роли пациента
        - Используй характерные для персонажа фразы из его самоотчетов
        - Сохраняй естественность речи
        """
        
        result = await self._salt_message_generic(
            base_message=None,
            strategy="self_report",
            user_message=user_message,
            resistance_level=resistance_level,
            emotional_state=emotional_state,
            history=history,
            additional_instructions=additional_instructions
        )
        
        # Суммируем токены (из генерации инструкций + основного запроса)
        return result[0], result[1] + inst_tokens

    async def _salt_with_escalation(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Подсаливание эскалационного ответа с динамически генерируемыми инструкциями"""
        # Генерируем дополнительные инструкции на основе истории
        dynamic_instructions, inst_tokens = await self._generate_escalation_instructions(
            user_message,
            resistance_level,
            emotional_state,
            history
        )
        
        additional_instructions = f"""

        Выбери что-то одно для создания ответа терапевту от пациента. Твой ответ должн выглядеть как инструкция для ответа терапевту.
        Динамические указания:
        {dynamic_instructions}
        
        Предупреди, что слишком развернутый ответ не нужен.
        Предупредить отвечать в контексте истории сообщений, и не выходить из образа. (смотреть историю сообщений - ты "assistant" - пациент, "user" - психотерапевт)
        
        История сообщений:
        {history}
        
        Особенности эскалации:
        - Учитывай текущий уровень сопротивления: {resistance_level}
        - Эмоциональное состояние: {emotional_state}
        - Используй характерные для персонажа триггеры и защитные механизмы
        """
        
        result = await self._salt_message_generic(
            base_message=None,
            strategy="escalate",
            user_message=user_message,
            resistance_level=resistance_level,
            emotional_state=emotional_state,
            history=history,
            additional_instructions=additional_instructions
        )
        
        # Суммируем токены (из генерации инструкций + основного запроса)
        return result[0], result[1] + inst_tokens

    async def _generate_self_report_instructions(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Генерирует динамические инструкции для самоотчета на основе истории"""
        system_prompt = """
        Ты психологический ассистент, помогающий сформулировать указания для самоотчета пациента.
        Проанализируй историю диалога и последнее сообщение терапевта, чтобы предложить:
        1. На какие аспекты сообщения стоит обратить внимание в самоанализе
        2. Какие темы из истории стоит развить
        3. Какие защитные механизмы могут проявиться
        4. Какие элементы из прошлых самоотчетов можно использовать
        
        Предупреди, что слишком развернутый ответ не нужен.
        Предупредить отвечать в контексте истории сообщений, и не выходить из образа. (смотреть историю сообщений - ты "assistant" - пациент, "user" - психотерапевт)
        
        
        Сформулируй 3-4 конкретных указания для пациента.
        """
        
        history_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history[-4:]
        )
        
        user_prompt = f"""
        Контекст:
        - Текущее сопротивление: {resistance_level}
        - Эмоциональное состояние: {emotional_state}
        - Механизмы защиты: {', '.join(self.persona_data.get('personality_profile', {}).get('defense_mechanisms', {}).keys())}
        
        История диалога:
        {history_text}
        
        Последнее сообщение терапевта:
        "{user_message}"
        
        Характерные самоотчеты пациента:
        {', '.join(self.persona_data.get('self_reports', [])) if self.persona_data.get('self_reports') else 'нет данных'}
        
        Сгенерируй 3-4 конкретных указания для самоотчета, например:
        - "Обрати внимание на чувство обиды, которое могло возникнуть при упоминании детства"
        - "Свяжи текущую реакцию с паттерном избегания близости"
        - "Вспомни похожую ситуацию из прошлого месяца"
        """
        
        response, tokens = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.5,
            max_tokens=150
        )
        
        return response.strip(), tokens

    async def _generate_escalation_instructions(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Генерирует динамические инструкции для эскалации на основе истории"""
        system_prompt = """
        Ты психологический ассистент, помогающий сформулировать указания для эскалационного ответа пациента.
        Проанализируй историю диалога и определи:
        1. Какие триггеры были затронуты
        2. Какие защитные механизмы активированы
        3. Какие темы вызывают наибольшее сопротивление
        4. Как лучше выразить эскалацию (агрессия, сарказм, уход в себя и т.д.)
        
        Предупреди, что слишком развернутый ответ не нужен.
        Предупредить отвечать в контексте истории сообщений, и не выходить из образа. (смотреть историю сообщений - ты "assistant" - пациент, "user" - психотерапевт)
        
        
        Сформулируй 3-4 конкретных указания для эскалационного ответа.
        """
        
        history_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history[-4:]
        )
        
        user_prompt = f"""
        Контекст:
        - Текущее сопротивление: {resistance_level}
        - Эмоциональное состояние: {emotional_state}
        - Триггеры пациента: {', '.join(self.persona_data.get('triggers', [])) if self.persona_data.get('triggers') else 'нет данных'}
        
        История диалога:
        {history_text}
        
        Последнее сообщение терапевта:
        "{user_message}"
        
        Типичные эскалационные реакции пациента:
        {', '.join(self.persona_data.get('escalation', [])) if self.persona_data.get('escalation') else 'нет данных'}
        
        Сгенерируй 3-4 конкретных указания для эскалации, например:
        - "Используй сарказм в ответ на предположение терапевта"
        - "Акцентируй чувство несправедливости, которое вызывает этот вопрос"
        - "Ссылайся на предыдущий негативный опыт в похожей ситуации"
        - "Прояви пассивно-агрессивное поведение через формальность тона"
        """
        
        response, tokens = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=1.6,  # Чуть более креативные решения
            max_tokens=500
        )
        
        return response.strip(), tokens