from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import Tariff, TariffType
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Начать сессию", callback_data="main_start_session")],
        [InlineKeyboardButton(text="🎲 Случайный клиент", callback_data="random_session")],
        [InlineKeyboardButton(text="👤 Мой профиль и покупки", callback_data="profile")],
        [InlineKeyboardButton(text="📚 Помощь", callback_data="help")],
        [InlineKeyboardButton(text="💬 Отзывы и предложения", callback_data="feedback_menu")],
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

def end_session_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔚 Завершить сессию", callback_data="end_session")]
        ]
    )

def session_resistance_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Среднее", callback_data="resistance_medium")],
        [InlineKeyboardButton(text="🔴 Высокое", callback_data="resistance_high")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])

def session_emotion_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😢 Тревожный и ранимый", callback_data="emotion_anxious")],
        [InlineKeyboardButton(text="😡 Агрессивно настроенный", callback_data="emotion_aggressive")],
        [InlineKeyboardButton(text="🧊 Холодный, отстранённый", callback_data="emotion_cold")],
        [InlineKeyboardButton(text="😶 Закрытый, в шоке", callback_data="emotion_shocked")],
        [InlineKeyboardButton(text="😭 На грани срыва", callback_data="emotion_breakdown")],
        [InlineKeyboardButton(text="🙃 Поверхностно весёлый, избегает тем", callback_data="emotion_superficial")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_resistance")]
    ])

def session_confirm_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟣 Начать сессию", callback_data="session_confirm_start")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])
    

def profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        # [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="my_achievements")], # совершенно не нужно
        [InlineKeyboardButton(text="📦 Приобрести подписку", callback_data="buy")],
        [InlineKeyboardButton(text="📊 Мои сессии и отчёты", callback_data="my_sessions")],
        [InlineKeyboardButton(text="🤝 Партнерская пограмма", callback_data="referral")],
        # [InlineKeyboardButton(text="🎯 Мои цели", callback_data="not_implemented")], # пока уберу
        [InlineKeyboardButton(text="🏅 Мои достижения", callback_data="my_achievements")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")],
    ])
    
def back_to_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="back_profile")]
    ])

def referral_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мои приглашённые", callback_data="my_referrals")],
        [InlineKeyboardButton(text="❓ Как это работает", callback_data="how_referral_works")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_main")],
    ])

def help_detail_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔘 Как начать сессию", callback_data="help_start_session")],
        [InlineKeyboardButton(text="📄 Что происходит после сессии", callback_data="help_after_session")],
        [InlineKeyboardButton(text="💡 Часто задаваемые вопросы", callback_data="help_faq")],
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
    
async def subscription_keyboard(session: AsyncSession) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру с тарифами из БД"""
    result = await session.execute(
        select(Tariff)
        .where(Tariff.is_active == True)
        .where(Tariff.name.in_([TariffType.START, TariffType.PRO, TariffType.UNLIMITED]))
        .order_by(Tariff.price)
    )
    tariffs = result.scalars().all()
    
    buttons = []
    for tariff in tariffs:
        price_rub = tariff.price / 100
        days = tariff.duration_days
        button_text = f"{tariff.display_name} — {price_rub:.0f} ₽ / {days} дней"
        
        # Добавляем иконки в зависимости от тарифа
        if tariff.name == TariffType.START:
            button_text = "🟢 " + button_text
        elif tariff.name == TariffType.PRO:
            button_text = "🔵 " + button_text
        elif tariff.name == TariffType.UNLIMITED:
            button_text = "⚫ " + button_text
        
        buttons.append(
            [InlineKeyboardButton(text=button_text, callback_data=f"activate_{tariff.name.value}")]
        )
    
    # Добавляем кнопку возврата
    buttons.append([InlineKeyboardButton(text="🔙 В профиль", callback_data="profile")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def subscription_keyboard_when_sessions_left(session: AsyncSession) -> InlineKeyboardMarkup:
    """Клавиатура при исчерпании сессий (без кнопки профиля)"""
    result = await session.execute(
        select(Tariff)
        .where(Tariff.is_active == True)
        .where(Tariff.name.in_([TariffType.START, TariffType.PRO, TariffType.UNLIMITED]))
        .order_by(Tariff.price)
    )
    tariffs = result.scalars().all()
    
    buttons = []
    for tariff in tariffs:
        price_rub = tariff.price / 100
        days = tariff.duration_days
        button_text = f"{tariff.display_name} — {price_rub:.0f} ₽ / {days} дней"
        
        if tariff.name == TariffType.START:
            button_text = "🟢 " + button_text
        elif tariff.name == TariffType.PRO:
            button_text = "🔵 " + button_text
        elif tariff.name == TariffType.UNLIMITED:
            button_text = "⚫ " + button_text
        
        buttons.append(
            [InlineKeyboardButton(text=button_text, callback_data=f"activate_{tariff.name.value}")]
        )
    
    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def persona_selection_menu(personas: list[str]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"🧍 {p}", callback_data=f"persona_{p}")]
        for p in personas
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_emotion")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def sessions_keyboard(sessions: list, page: int = 0, per_page: int = 5):
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки для каждой сессии
    for session in sessions[page*per_page:(page+1)*per_page]:
        builder.row(
            InlineKeyboardButton(
                text=f"{session.persona_name or 'Без персонажа'} - {session.started_at.strftime('%d.%m %H:%M')}",
                callback_data=f"session_detail_{session.id}"
            )
        )
    
    # Добавляем пагинацию
    if len(sessions) > per_page:
        if page > 0:
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"sessions_page_{page-1}")
            )
        if (page+1)*per_page < len(sessions):
            builder.row(
                InlineKeyboardButton(text="Вперед ➡️", callback_data=f"sessions_page_{page+1}")
            )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_profile")
    )
    
    return builder.as_markup()

from aiogram.utils.keyboard import InlineKeyboardBuilder

def session_details_keyboard(session_id: int):
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="📩 Мои сообщения",
            callback_data=f"show_user_messages_{session_id}"
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="🤖 Ответы бота",
            callback_data=f"show_bot_messages_{session_id}"
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="📄 Отчёт",
            callback_data=f"show_report_{session_id}"
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="🔙 Назад к списку",
            callback_data="back_to_sessions_list"
        )
    )
    
    return builder.as_markup()