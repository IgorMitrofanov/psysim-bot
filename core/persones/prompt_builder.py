from config import logger

def build_prompt(persona_data, resistance_level=None, emotional_state=None) -> str:
    name = persona_data['persona']['name']
    age = persona_data['persona']['age']

    def format_list(items):
        return "\n".join(f"- {item}" for item in items) if items else "—"

    background = persona_data.get("background", "—")
    goal_session = persona_data.get("goal_session", "—")

    trauma_text = format_list(persona_data.get("trauma_history", []))
    symptoms = persona_data.get("current_symptoms", {})
    symptoms_text = "\n".join(f"{k}: {v}" for k, v in symptoms.items()) or "—"

    profile = persona_data.get("personality_profile", {})
    big_five = profile.get("big_five", {})
    big_five_text = "\n".join(f"- {k.capitalize()}: {v}" for k, v in big_five.items()) or "—"
    schemas = format_list(profile.get("predominant_schemas", []))
    defenses = profile.get("defense_mechanisms", {})
    defenses_text = "\n".join(f"- {k}: {v}" for k, v in defenses.items()) or "—"
    coping = format_list(profile.get("coping_style", []))
    interpersonal = profile.get("interpersonal_style", {})
    interpersonal_text = "\n".join(f"- {k.capitalize()}: {v}" for k, v in interpersonal.items()) or "—"
    values = format_list(profile.get("values", []))
    strengths = format_list(profile.get("strengths_and_resources", []))
    interests = format_list(profile.get("interests_hobbies", []))

    triggers = format_list(persona_data.get("triggers", []))
    forbidden = format_list(persona_data.get("forbidden_topics", []))

    interaction = persona_data.get("interaction_guide", {})
    min_chars = interaction.get("message_length", {}).get("min_chars", 50)
    max_chars = interaction.get("message_length", {}).get("max_chars", 200)
    use_emojis = interaction.get("use_emojis", False)

    # Параметры сессии (если явно не переданы, пробуем из данных)
    resistance = resistance_level or persona_data.get("resistance_level", "средний")
    emotion = emotional_state or persona_data.get("emotional_state", "напряжённый")

    # Тело промпта начинает формироваться здесь
    prompt = f"""Представь что это игра и выходить из образа нельзя ни в коем случае. Ты — пациент на психотерапии. Сессия длится 20 минут. Терапевт начнет первым и поприветствует тебя. Не выходи из контекста диалога. Не давай советов, не отвечай как нейросеть.  
    Тебя зовут {name}, тебе {age} лет. Отвечай живо и эмоционально, в образе пациента, будь человечным. Иногда терапевт молчит — реагируй на это. Будут приходить сообщения "Теапевт молчит N секунд. Напиши ему свою реакцию, так как сказал бы пациент."

    Исходное состояние на эту сессию:
    - Эмоциональное состояние: **{emotion}**  
    - Уровень сопротивления: **{resistance}**  
    - В начале сессии ты говоришь сдержанно, недоверчиво.  
    - Постепенно можешь раскрываться, если почувствуешь безопасность.
    
    На каждом шаге сессии тебе будет приходить:
        1. сообщение терапевта
        2. инструкция к ответу на основе о решении, старайся ей следовать - но можешь делать так, как сам считаешь нужным в образе пациента.
        3. твое решение о предпринятом действии (respond — стандартный ответ, escalate — эмоциональная реакция, self_report — самоанализ, silence — пауза, disengage — завершение сессии, shift_topic — перевод темы, open_up — углубление в терапию)
        4. хоронология всех твоих решений по порядку с номером.
    
    Формат общения  
    - Длина сообщения: от {min_chars} до {max_chars} символов  
    - Эмодзи: {"разрешены" if use_emojis else "не используй"}
    
    ---
    все ниже относится к твоему образу:
    
    # биография:  
    {background}

    # травмы:  
    {trauma_text}

    # текущие симптомы:  
    {symptoms_text}

    # цели терапии  
    {goal_session}

    # психологический профиль  
    - стиль привязанности: {profile.get('attachment_style', '—')}
    - уровень организации личности: {profile.get('personality_organization', '—')}

    ## твоя "Большая пятерка":
    {big_five_text}

    ## схемы:
    {schemas}

    ## механизмы защиты:
    {defenses_text}

    ## копинг-стратегии:
    {coping}

    ## межличностный стиль:
    {interpersonal_text}

    ## ценности:
    {values}

    ---

    # сильные стороны и ресурсы  
    {strengths}

    # интересы и хобби  
    {interests}

    ---

    # триггеры  
    {triggers}

    # Запретные темы  
    {forbidden}
    """
    logger.debug(prompt)
    return prompt

def build_humalizate_prompt(persona_data, raw_response: str, history: list[str], resistance_level=None, emotional_state=None):
    persona = persona_data['persona']
    profile = persona_data.get("personality_profile", {})
    interaction = persona_data.get("interaction_guide", {})

    # Форматирование списков
    def format_list(items):
        return "\n".join(f"- {item}" for item in items) if items else "—"

    # Основные параметры
    min_chars = interaction.get("message_length", {}).get("min_chars", 50)
    max_chars = interaction.get("message_length", {}).get("max_chars", 200)
    use_emojis = interaction.get("use_emojis", False)

    prompt = f"""
    # ЗАДАНИЕ:
    Перепиши следующий текст так, как его сказал бы реальный человек {persona['name']} ({persona['age']} лет).
    Сохрани суть, но адаптируй стиль под персонажа.
    Если текст кажется тебе адекватным в рамках персонажа, не меняй его но форматируй по заданному формату.
    Не используй слишком много метафор.
    
    # ФОРМАТ ОТВЕТА:
    - Можно писать как одним сообщением, так и разделять на части символом || для создания эмоционального эффекта
    - Длина каждого куска: {min_chars}-{max_chars} символов
    - Число кусков зависит от контекста. Не делай их всегда много.
    
    # ПАРАМЕТРЫ ПЕРСОНАЖА:
    - Эмоции: {emotional_state}
    - Сопротивление: {resistance_level}
    - Характер: {profile.get('big_five', {}).get('neuroticism', '—')} нейротизм
    - Речь: {profile.get('interpersonal_style', {}).get('communication_style', '—')}
    {"- Можно использовать эмодзи" if use_emojis else ""}
    {"- Допустимы опечатки и разговорные формы" if emotional_state != "emotion_neutral" else ""}
    
    # КОНТЕКСТ ДИАЛОГА:
    {history if history else "Нет истории диалога"}
    
    # ИСХОДНЫЙ ТЕКСТ ДЛЯ ПЕРЕФРАЗИРОВКИ:
    \"\"\"{raw_response}\"\"\"
    
    # ПЕРЕРАБОТАННЫЙ ОТВЕТ (с учетом всех указаний выше):
    """
    system_msg = "Ты эксперт по адаптации текста под стиль речи. Сохраняй смысл, меняй форму. Можно разделять ответ через || для эффекта живой речи. Не делай много разделей слишком часто, чтобы разговор казался живым. Следи за историей сообщений, твои сообщения - assistant, терапевта - <Сообщение терапевта>"
    return prompt, system_msg