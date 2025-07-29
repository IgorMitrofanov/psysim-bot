from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import Tariff
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import TariffType

async def create_default_tariffs(session: AsyncSession):
    """Создаёт стандартные тарифы в БД при первом запуске"""
    default_tariffs = [
        {
            "name": TariffType.TRIAL,
            "display_name": "Пробный",
            "price": 0,
            "duration_days": 999,
            "session_quota": 1,
            "quota_period_days": 30,
            "description": "Бесплатный базовый тариф с ограниченным функционалом"
        },
        {
            "name": TariffType.START,
            "display_name": "Старт",
            "price": 59000,
            "duration_days": 7,
            "session_quota": 3,
            "quota_period_days": 7,
            "description": "Базовый платный тариф на неделю"
        },
        {
            "name": TariffType.PRO,
            "display_name": "Профессиональный",
            "price": 149000,
            "duration_days": 30,
            "session_quota": 10,
            "quota_period_days": 30,
            "description": "Расширенный тариф для профессионалов"
        },
        {
            "name": TariffType.UNLIMITED,
            "display_name": "Безлимитный",
            "price": 249000,
            "duration_days": 30,
            "session_quota": 999,
            "quota_period_days": 0,
            "description": "Полный доступ без ограничений"
        }
    ]

    for tariff_data in default_tariffs:
        existing = await session.execute(
            select(Tariff).where(Tariff.name == tariff_data["name"])
        )
        if not existing.scalar_one_or_none():
            new_tariff = Tariff(**tariff_data)
            session.add(new_tariff)
    
    await session.commit()