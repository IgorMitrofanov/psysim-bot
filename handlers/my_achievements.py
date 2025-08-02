from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import Achievement, AchievementType, AchievementTier
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from aiogram import Router, types
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user
from services.achievements import AchievementSystem
from keyboards.builder import profile_keyboard


router = Router(name="my_achievements")

@router.callback_query(lambda c: c.data == "my_achievements")
async def my_achievements_handler(callback: types.CallbackQuery, session: AsyncSession, achievement_system: AchievementSystem):
    # Получаем пользователя
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    # Получаем все достижения пользователя
    stmt = select(Achievement).where(
        Achievement.user_id == db_user.id
    ).order_by(
        Achievement.awarded_at.desc()
    )
    result = await session.execute(stmt)
    achievements = result.scalars().all()

    if not achievements:
        await callback.message.edit_text(
            "🎖 У вас пока нет достижений.\n"
            "Продолжайте использовать бота, чтобы их получить!",
            reply_markup=profile_keyboard()
        )
        return

    # Группируем достижения по типам
    achievements_by_type = {}
    for ach in achievements:
        if ach.badge_code not in achievements_by_type:
            achievements_by_type[ach.badge_code] = []
        achievements_by_type[ach.badge_code].append(ach)

    # Формируем текст сообщения
    message_text = "🏆 Ваши достижения:\n\n"
    
    # Получаем сервис достижений
    progress_data = await achievement_system.get_user_progress(db_user.id) if achievement_system else {}

    for ach_type, ach_list in achievements_by_type.items():
        # Получаем информацию о прогрессе
        progress_info = progress_data.get(ach_type, {})
        next_tier = progress_info.get('next_tier')
        next_required = progress_info.get('next_progress_required', 0)
        current_progress = progress_info.get('current_progress', 0)
        
        # Сортируем по уровню (от бронзы к платине)
        ach_list.sort(key=lambda x: x.tier.value)
        
        # Добавляем информацию о типе достижения
        type_name = achievement_system._get_achievement_name(ach_type) if achievement_system else ach_type.value
        message_text += f"<b>{type_name}</b>\n"
        
        # Добавляем полученные уровни
        for ach in ach_list:
            tier_name = achievement_system._get_tier_name(ach.tier) if achievement_system else ach.tier.value
            message_text += f"  - {tier_name} 🏅 (получено {ach.awarded_at.strftime('%d.%m.%Y')})\n"
        
        # Добавляем прогресс к следующему уровню
        if next_tier:
            tier_name = achievement_system._get_tier_name(next_tier) if achievement_system else next_tier.value
            message_text += (
                f"  ➔ Прогресс к {tier_name}: {current_progress}/{next_required}\n"
            )
        message_text += "\n"

    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")],
    ])

    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )