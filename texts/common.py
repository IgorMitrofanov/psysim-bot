BACK_TO_MENU_TEXT = (
    "Главное меню"
)

def profile_text(data: dict) -> str:
    base = (
        f"<b>👤 Профиль</b>\n"
        f"Никнейм: @{data['username']}\n"
        f"ID: <code>{data['telegram_id']}</code>\n"
        f"Дата регистрации: {data['registered_at']}\n"
        f"Тариф: {data['active_tariff']}\n"
    )

    if data["active_tariff"] != "Подписка не оформлена":
        base += f"Активна до: {data['tariff_expires']}\n"

    base += (
        f"Сессий пройдено: {data['sessions_done']}\n"
        f"Бонусные сессии: <b>{data['bonus_balance']}</b>\n"
        f"Баланс: <b>{data['balance']} ₽</b>\n"
    )

    if data["sessions_done"] > 0:
        base += f"Последний сценарий: {data['last_scenario']}"

    return base


def referral_text(ref_link: str, bonus_balance: int) -> str:
    return (
        f"<b>🎁 Партнёрская программа</b>\n"
        f"Скопируйте ссылку и отправьте друзьям:\n\n"
        f"<code>{ref_link}</code>\n\n"
        f"💰 Бонусные сессии: <b>{bonus_balance}</b>\n"
        f"👥 Каждый приглашённый = 1 бонусная сессия\n"
    )


def referral_stats_text(referrals: list) -> str:
    lines = [
        f"📊 <b>Приглашённые:</b> {len(referrals)} чел.",
        "",
    ]
    for r in referrals:
        status = "✅ Оплатил" if r.has_paid else "⏳ Не оплатил"
        lines.append(f"— <code>{r.invited_user_id}</code> • {status}")
    return "\n".join(lines)


def get_start_text(is_new: bool):
    if is_new:
        return (
            "👋 Привет! Рада приветствовать тебя в AI-тренажёре для психологов.\n\n"
            "Я — практикующий психолог и хорошо знаю, как сложно бывает начать практику: первый клиент, страх навредить, растерянность перед сопротивлением. Этот проект создан, чтобы помочь тебе безопасно и эффективно отработать навыки консультирования.\n\n"
            "🧠 Здесь ты сможешь:\n"
            "– потренироваться в живом диалоге с ИИ-клиентом,\n"
            "– выбрать уровень сложности и тему запроса,\n"
            "– получать супервизорский отчёт после каждой сессии — с разбором, что было хорошо, а где можно было поступить иначе.\n\n"
            "🤔 Почему не просто ChatGPT? У нас — реализм, сопротивление, сценарии и эмоции.\n\n"
            "🎁 Доступна бесплатная тестовая сессия. Начнем?"
        )
    else:
        return (
            "👋 Привет! Рада видеть тебя снова в тренажёре 🌱\n\n"
            "Ты можешь:\n"
            "🔹 Начать новую сессию\n"
            "🔹 Посмотреть прошлые отчёты\n"
            "🔹 Отслеживать свой прогресс\n"
            "🔹 Изучить рекомендации по улучшению\n\n"
            "Готов(а) к новой практике?"
        )