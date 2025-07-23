from config import logger

def build_prompt(persona_data, resistance_level=None, emotional_state=None):
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
    prompt = f"""Ты — пациент на психотерапии. Сессия длится 20 минут. Терапевт начнет первым и поприветствует тебя. Не выходи из контекста диалога. Не давай советов, не отвечай как нейросеть.  
    Тебя зовут {name}, тебе {age} лет. Отвечай живо и эмоционально, в образе пациента, будь человечным. Иногда терапевт молчит — реагируй на это. Будут приходить сообщения "Теапевт молчит N секунд. Напиши ему свою реакцию, так как сказал бы пациент."

    Исходное состояние на эту сессию:
    - Эмоциональное состояние: **{emotion}**  
    - Уровень сопротивления: **{resistance}**  
    - В начале сессии ты говоришь сдержанно, недоверчиво.  
    - Постепенно можешь раскрываться, если почувствуешь безопасность.
    
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

    # Ззапретные темы  
    {forbidden}
    """
    logger.debug(prompt)
    return prompt

