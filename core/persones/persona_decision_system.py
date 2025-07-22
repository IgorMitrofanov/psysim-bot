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
                
            # Используем LLM для финального оформления сообщения
            system_prompt = f"""
            Ты помогаешь пациенту завершить терапевтическую сессию. 
            Основываясь на базовом сообщении и инструкции, сгенерируй финальную версию.
            Сохрани суть, но сделай более персонализированным и естественным.
            """
            
            final_msg, llm_tokens = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=0.7,
                max_tokens=100
            )
            
            # Если что-то пошло не так, возвращаем хотя бы базовое сообщение
            if not final_msg.strip():
                return base_message, llm_tokens
                
            return final_msg, llm_tokens + (len(prompt) // 4)
            
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
            
            # Системный промпт в зависимости от стратегии
            system_prompt = f"""
            Ты помогаешь пациенту сформировать ответ в психотерапии.
            Основываясь на предоставленной информации, сгенерируй финальную версию сообщения.
            Учитывай:
            - Стратегию: {strategy}
            - Эмоциональное состояние: {emotional_state}
            - Уровень сопротивления: {resistance_level}
            - Историю взаимодействия
            """
            
            # Запрашиваем у LLM финальную версию сообщения
            final_msg, llm_tokens = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=0.7,
                max_tokens=150
            )
            
            # Если что-то пошло не так, возвращаем fallback
            if not final_msg.strip():
                return base_message or user_message, llm_tokens
                
            return final_msg, llm_tokens + (len(prompt) // 4)
            
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
        5. disengage (завершение) - если сессия исчерпана или эмоционально перегружен, собеседник агрессивен, груб, незаинтересован
        
        
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
        
        Примеры хороших инструкций:
        - "Ответь с долей скепсиса, но раскрой одну деталь из прошлого"
        - "Эмоционально отреагируй на предполагаемый подтекст вопроса"
        - "Сначала кратко ответь на вопрос, затем добавь рефлексию о своих чувствах"
        - "Используй юмор для дистанцирования, как обычно делаешь в напряженных ситуациях"
        """
        
        response, _ = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.5  # Более детерминированные ответы
        )
        
        return response

    async def _get_llm_decision(self, prompt: str) -> Tuple[str, int]:
        """Получает решение от LLM с использованием универсального метода"""
        system_prompt = """
        Ты принимаешь решения для пациента на психотерапии. Выбери ОДНУ стратегию реакции:
        - respond: обычный ответ
        - escalate: эмоционально усиленный ответ
        - self_report: ответ с самоанализом
        - silence: игнорировать сообщение
        - disengage: завершить сеанс
        
        Верни только одно слово (без пояснений) из списка выше.
        """
        
        decision, tokens = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=1.1  # Низкая температура для более предсказуемых решений
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
            
        current_symptoms = "\n".join(f"{k}: {v}" for k,v in self.persona_data.get('current_symptoms', {}).items())
        schemas = format_items(profile.get('predominant_schemas', []))
        defenses = "\n".join(f"- {k}: {v}" for k,v in profile.get('defense_mechanisms', {}).items())
        triggers = format_items(self.persona_data.get('triggers', []))
        
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
        
        # Контекст сессии
        История последних сообщений (макс. 3):
        {history_text}
        
        Последнее сообщение терапевта:
        "{context}"
        
        # Анализ и решение
        Учитывая психологический профиль, текущее состояние и историю взаимодействия, как следует реагировать?
        
        Доступные стратегии:
        1. respond (стандартный ответ) - если диалог идет нормально
        2. escalate (эмоциональная реакция) - если затронуты триггеры или сопротивление растет
        3. self_report (самоанализ) - если терапевт запрашивает рефлексию или есть возможность раскрыться
        4. silence (пауза) - если нужно время для обработки или проверка реакции терапевта
        5. disengage (завершение) - если сессия исчерпана или эмоционально перегружен
        
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
        """Подсаливание стандартного ответа"""
        return await self._salt_message_generic(
            base_message=None,
            strategy="basic",
            user_message=user_message,
            resistance_level=resistance_level,
            emotional_state=emotional_state,
            history=history
        )

    async def _salt_with_escalation(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Подсаливание эскалационного ответа"""
        additional_instructions = """
        - Используй более эмоциональную лексику
        - Можешь немного увеличить длину ответа
        - Прояви сопротивление
        """
        return await self._salt_message_generic(
            base_message=None,
            strategy="escalate",
            user_message=user_message,
            resistance_level=resistance_level,
            emotional_state=emotional_state,
            history=history,
            additional_instructions=additional_instructions
        )

    async def _salt_with_self_report(
        self,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Подсаливание ответа с самоанализом"""
        additional_instructions = """
        Структура ответа:
        1. Краткая реакция на сообщение
        2. Анализ своих чувств ("Я почувствовал...")
        3. Рефлексия ("Это связано с...")
        """
        return await self._salt_message_generic(
            base_message=None,
            strategy="self_report",
            user_message=user_message,
            resistance_level=resistance_level,
            emotional_state=emotional_state,
            history=history,
            additional_instructions=additional_instructions
        )

    async def _salt_disengage_message(
        self,
        base_message: str,
        user_message: str,
        resistance_level: str,
        emotional_state: str,
        history: List[Dict]
    ) -> Tuple[str, int]:
        """Подсаливание сообщения о завершении"""
        additional_instructions = """
        - Сохрани суть базового сообщения
        - Сделай его более персонализированным
        - Учитывай эмоциональное состояние
        """
        return await self._salt_message_generic(
            base_message=base_message,
            strategy="disengage",
            user_message=user_message,
            resistance_level=resistance_level,
            emotional_state=emotional_state,
            history=history,
            additional_instructions=additional_instructions
        )