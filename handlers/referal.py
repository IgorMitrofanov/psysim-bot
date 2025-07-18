from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import get_user, get_user_referrals
from keyboards.builder import profile_keyboard, referral_keyboard
from texts.common import profile_text, referral_text, referral_stats_text
from config import logger
from keyboards.builder import main_menu

from texts.referral_texts import (
    HOW_REFERRAL_WORKS_TEXT,
    NO_PROFILE_OR_CODE_TEXT,
    NO_REFERRALS_TEXT,
    NO_PROFILE_ALERT,
    COPY_LINK_ALERT_TEMPLATE
)

router = Router(name="referal")

@router.callback_query(lambda c: c.data == "referral")
async def referral_handler(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user or not db_user.referral_code:
        await callback.message.edit_text(NO_PROFILE_OR_CODE_TEXT)
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
        await callback.answer(NO_PROFILE_ALERT, show_alert=True)
        return

    referrals = await get_user_referrals(session, db_user.id)
    if not referrals:
        await callback.answer(NO_REFERRALS_TEXT, show_alert=True)
        return
    
    text = referral_stats_text(referrals)
    await callback.message.edit_text(text, reply_markup=referral_keyboard())

@router.callback_query(lambda c: c.data == "how_referral_works")
async def how_referral_works_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(HOW_REFERRAL_WORKS_TEXT, reply_markup=referral_keyboard())

