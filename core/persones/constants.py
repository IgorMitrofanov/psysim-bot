class PersonaConstants:
    """
    Константы и настройки для поведения персонажа.
    """
    SILENCE_PROMPTS = [
            "Терапевт молчит. Стоит тишина. Пожалуйста, реагируй на тишину в контексте переписки. Это важно",
    ]
    MAX_SILENCE_PENALTY = 5  # Максимальное усиление негатива при молчании подряд
    REPEAT_RESPONSE_THRESHOLD = 0.8  # Порог для повторения ответа (0-1, чем выше строже)
    ESCALATION_COOLDOWN_TICKS = 20  # Минимальное количество тиков между эскалациями
