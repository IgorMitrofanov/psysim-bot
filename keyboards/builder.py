from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Начать сессию", callback_data="start_session")],
        [InlineKeyboardButton(text="📊 Мои сессии и отчёты", callback_data="my_sessions")],
        [InlineKeyboardButton(text="👤 Мой профиль и покупки", callback_data="profile")],
        [InlineKeyboardButton(text="📚 Помощь", callback_data="help")],
        [InlineKeyboardButton(text="💬 Отзывы и предложения", callback_data="feedback_menu")],
        [InlineKeyboardButton(text="🤝 Партнерская пограмма", callback_data="referral")],
        [InlineKeyboardButton(text="🎯 Мои цели", callback_data="goals")],
        [InlineKeyboardButton(text="🏅 Мои достижения", callback_data="achievements")],
    ])

def feedback_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data="leave_feedback")],
        [InlineKeyboardButton(text="📌 Предложить улучшение", callback_data="suggest_feature")],
        [InlineKeyboardButton(text="⚠️ Сообщить об ошибке", callback_data="report_error")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")],
    ])
    
def cancel_feedback_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_feedback")]
    ])

def free_session_resistance_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Среднее", callback_data="resistance_medium")],
        [InlineKeyboardButton(text="🔴 Высокое", callback_data="resistance_high")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])

def free_session_emotion_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😢 Тревожный и ранимый", callback_data="emotion_anxious")],
        [InlineKeyboardButton(text="😡 Агрессивно настроенный", callback_data="emotion_aggressive")],
        [InlineKeyboardButton(text="🧊 Холодный, отстранённый", callback_data="emotion_cold")],
        [InlineKeyboardButton(text="😶 Закрытый, в шоке", callback_data="emotion_shocked")],
        [InlineKeyboardButton(text="😭 На грани срыва", callback_data="emotion_breakdown")],
        [InlineKeyboardButton(text="🙃 Поверхностно весёлый, избегает тем", callback_data="emotion_superficial")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_resistance")]
    ])

def free_session_format_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Текст", callback_data="format_text")],
        [InlineKeyboardButton(text="🎧 Аудио", callback_data="format_audio")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_emotion")]
    ])

def free_session_confirm_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟣 Начать сессию", callback_data="start_free_session")],
        [InlineKeyboardButton(text="🔚 Завершить сессию", callback_data="end_free_session")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])

def profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Продлить подписку", callback_data="extend_subscription")],
        [InlineKeyboardButton(text="📦 Купить пакет сессий", callback_data="buy_sessions")],
        [InlineKeyboardButton(text="🧾 Посмотреть тарифы", callback_data="view_tariffs")],
        [InlineKeyboardButton(text="📊 Мои сессии и отчёты", callback_data="my_sessions")],
        [InlineKeyboardButton(text="💬 Связаться с поддержкой", callback_data="support_contact")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")],
    ])

def referral_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Скопировать ссылку", callback_data="copy_referral_link")],
        [InlineKeyboardButton(text="📊 Мои приглашённые", callback_data="my_referrals")],
        [InlineKeyboardButton(text="❓ Как это работает", callback_data="how_referral_works")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_main")],
    ])

def help_detail_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔘 Как начать сессию", callback_data="help_start_session")],
        [InlineKeyboardButton(text="📄 Что происходит после сессии", callback_data="help_after_session")],
        [InlineKeyboardButton(text="💡 Часто задаваемые вопросы", callback_data="help_faq")],
        [InlineKeyboardButton(text="📞 Связаться с поддержкой", callback_data="support_contact")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])

def help_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="help")]
    ])

def back_to_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])