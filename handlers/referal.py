from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import get_user, get_referrals_by_user
from keyboards.builder import profile_keyboard, referral_keyboard
from texts.common import profile_text, referral_text, referral_stats_text
from config import logger
from keyboards.builder import main_menu

router = Router(name="referal")

@router.callback_query(lambda c: c.data == "referral")
async def referral_handler(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user or not db_user.referral_code:
        await callback.message.edit_text("Профиль не найден или отсутствует реферальный код.")
        return

    bot_name = (await callback.bot.get_me()).username
    ref_link = f"https://t.me/{bot_name}?start=ref_{db_user.referral_code}"

    await callback.message.edit_text(
        referral_text(ref_link=ref_link, bonus_balance=db_user.bonus_balance),
        reply_markup=referral_keyboard()
    )


@router.callback_query(lambda c: c.data == "my_referrals")
async def my_referrals_handler(callback: types.CallbackQuery, session: AsyncSession):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    referrals = await get_referrals_by_user(session, db_user.id)
    if not referrals:
        await callback.answer("У вас пока нет приглашённых.", show_alert=True)
        return

    text = referral_stats_text(referrals)
    await callback.message.edit_text(text, reply_markup=referral_keyboard())

@router.callback_query(lambda c: c.data == "how_referral_works")
async def how_referral_works_handler(callback: types.CallbackQuery):
    text = (
        "❓ <b>Как работает партнёрка:</b>\n\n"
        "1. Скопируйте свою ссылку и отправьте другу.\n"
        "2. Когда он запустит бота и оплатит подписку, вы получите бонус 🎁\n"
        "3. Бонусы можно потратить на бесплатные сессии или скидки на тариф.\n\n"
        "<i>1 бонус = 1 сессия или 10% скидки</i>"
    )
    await callback.message.edit_text(text, reply_markup=referral_keyboard())

@router.callback_query(lambda c: c.data == "copy_referral_link")
async def copy_referral_link_handler(callback: types.CallbackQuery, session: AsyncSession):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    bot_name = (await callback.bot.get_me()).username
    ref_link = f"https://t.me/{bot_name}?start=ref_{db_user.id}"
    await callback.answer(f"Скопируйте ссылку:\n{ref_link}", show_alert=True)
