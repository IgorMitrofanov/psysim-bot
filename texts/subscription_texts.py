from typing import Dict
from config import config
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import Tariff

SUBSCRIPTION_EXPIRED_TEXT = (
    "🔔 Ваша подписка истекла.\n\n"
    "Все функции переведены на бесплатный тариф с ограниченными возможностями. "
    "Чтобы продолжить пользоваться полным функционалом — обновите подписку в меню тарифов."
)

SUBSCRIPTION_WILL_EXPIRE_SOON_TEXT = (
    "🔔 Ваша подписка истекает через {days_left} дня(дней).\n\n"
)

async def get_tariff_menu_text(db_session: AsyncSession) -> str:
    """Генерирует текст меню тарифов на основе данных из БД"""
    # Получаем все активные тарифы из БД
    result = await db_session.execute(
        select(Tariff).where(Tariff.is_active == True).order_by(Tariff.price)
    )
    tariffs = result.scalars().all()
    
    if not tariffs:
        return "❌ На данный момент нет доступных тарифов"
    
    menu_text = """<b>💳 Актуализированные тарифы AI-тренажёра для психологов</b>
Во всех тарифах: выбор персонажей (тематика + уровень сопротивления), супервизорский отчёт после каждой сессии, система достижений и бейджи.
________________________________________
"""
    
    # Символы для маркировки тарифов
    tariff_icons = ["🔹", "🔸", "🔷", "🔶", "⭐"]
    
    for i, tariff in enumerate(tariffs):
        icon = tariff_icons[i] if i < len(tariff_icons) else "▪️"
        
        # Форматируем описание тарифа
        tariff_block = f"""
{icon} <b>{tariff.display_name}</b>
• {f'{tariff.session_quota} сессий' if tariff.session_quota < 999 else 'безлимит сессий'} – {tariff.price / 100} ₽
"""
        # Добавляем срок действия только если это не триал
        if "trial" not in tariff.name.value.lower():
            tariff_block += f"• 🕒 Доступ на {tariff.duration_days} дней\n"
        
        tariff_block += """• 🎭 Выбор персонажей, тем и уровней сопротивления
"""
        
        # Добавляем специфические фичи для разных тарифов
        if "pro" in tariff.name.value.lower():
            tariff_block += "• 💬 Текстовый + 🎧 Аудио-режим\n"
            tariff_block += "• 🔁 Повторение и прокачка сценариев\n"
        elif "unlimited" in tariff.name.value.lower():
            tariff_block += "• 💬 Текстовый + 🎧 Аудио-режим\n"
            tariff_block += "• 📊 Ежемесячный сводный отчёт\n"
            tariff_block += "• 🎯 Отслеживание целей\n"
            tariff_block += "• 👥 Приоритетная поддержка\n"
        else:  # Стандартные фичи
            tariff_block += "• 💬 Текстовый режим\n"
        
        tariff_block += "• 📄 Супервизорский отчёт\n"
        tariff_block += "• 🏅 Бейджи и достижения\n"
        tariff_block += "________________________________________"
        
        menu_text += tariff_block
    
    menu_text += "\nНачни практику уже сегодня — выбирай тариф и погружайся в реалистичные сценарии!"
    
    return menu_text



# Общие текстовые шаблоны
UNKNOWN_TARIFF = "❌ Неизвестный тариф"

async def get_tariff_success_text(tariff: Tariff) -> str:
    """Генерирует текст об успешной активации тарифа"""
    return (
        f"✅ Подписка «{tariff.display_name}» успешно активирована на {tariff.duration_days} дней.\n"
        f"С вас списано {tariff.price / 100} ₽.\n\n"
        f"Доступно сессий: {tariff.session_quota if tariff.session_quota < 999 else 'безлимит'}"
    )

TARIFF_FAIL_FUNDS = "❌ Недостаточно средств на балансе. Пожалуйста, пополните баланс."
TARIFF_USER_NOT_FOUND = "❌ Пользователь не найден. Попробуйте заново."

SUBSCRIPTION_EXPIRED_TEXT = (
    "🔔 Ваша подписка истекла.\n"
    "Чтобы продолжить пользоваться сервисом — выберите тариф в меню."
)

async def get_tariff_map(db_session: AsyncSession) -> Dict[str, Tariff]:
    """Возвращает словарь тарифов для обработки callback-ов"""
    result = await db_session.execute(select(Tariff).where(Tariff.is_active == True))
    tariffs = result.scalars().all()
    
    return {
        f"activate_{tariff.name}": tariff
        for tariff in tariffs
    }