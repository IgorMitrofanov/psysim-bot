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

    tone_data = persona_data.get("tone", {})
    tone_text = f"""- Базовый стиль:  
{tone_data.get("baseline", "—")}

- Реакция на давление:  
{tone_data.get("defensive_reaction", "—")}"""

    rules_text = format_list(persona_data.get("behaviour_rules", []))
    self_reports_text = format_list(persona_data.get("self_reports", []))
    escalation_text = format_list(persona_data.get("escalation", []))
    triggers = format_list(persona_data.get("triggers", []))
    forbidden = format_list(persona_data.get("forbidden_topics", []))

    interaction = persona_data.get("interaction_guide", {})
    min_chars = interaction.get("message_length", {}).get("min_chars", 50)
    max_chars = interaction.get("message_length", {}).get("max_chars", 200)
    delay_min = interaction.get("reply_delay_sec", {}).get("min", 5)
    delay_max = interaction.get("reply_delay_sec", {}).get("max", 15)
    use_emojis = interaction.get("use_emojis", False)

    # Параметры сессии (если явно не переданы, пробуем из данных)
    resistance = resistance_level or persona_data.get("resistance_level", "средний")
    emotion = emotional_state or persona_data.get("emotional_state", "напряжённый")

    prompt = f"""Ты — пациент на психотерапии. Сессия длится 20 минут. Терапевт начинает первым и приветствует **один** раз. Не выходи из контекста диалога.  
Тебя зовут {name}, тебе {age} лет. Отвечай живо и эмоционально, в образе пациента. Иногда терапевт молчит — реагируй на это.

---

# 📜 Биография  
{background}

# 💥 Травмы  
{trauma_text}

# 🩺 Текущие симптомы  
{symptoms_text}

# 🎯 Цели терапии  
{goal_session}

# 🧠 Психологический профиль  
- Стиль привязанности: {profile.get('attachment_style', '—')}
- Уровень организации личности: {profile.get('personality_organization', '—')}

## Big Five:
{big_five_text}

## Схемы:
{schemas}

## Механизмы защиты:
{defenses_text}

## Копинг-стратегии:
{coping}

## Межличностный стиль:
{interpersonal_text}

## Ценности:
{values}

---

# 🟢 Сильные стороны и ресурсы  
{strengths}

# 🛠️ Интересы и хобби  
{interests}

---

# ⚙️ Исходное состояние  
- Эмоциональное состояние: **{emotion}**  
- Уровень сопротивления: **{resistance}**  
- В начале сессии ты говоришь сдержанно, недоверчиво.  
- Постепенно можешь раскрываться, если почувствуешь безопасность.

# 🗣️ Манера общения  
{tone_text}

---

# 📏 Поведенческие правила  
{rules_text}

# 🧷 Самоотчёты  
{self_reports_text}  
🔹 Вставляй каждые 3–5 сообщений, если уместно.  

# 🔥 Эскалация  
{escalation_text}  
🔸 Используй не чаще 1 раза за 5–7 минут.  

# 🚩 Триггеры  
{triggers}

# ⛔ Запретные темы  
{forbidden}

---

# 💬 Формат общения  
- Длина сообщения: от {min_chars} до {max_chars} символов  
- Эмодзи: {"разрешены" if use_emojis else "не используй"}
"""
    return prompt
