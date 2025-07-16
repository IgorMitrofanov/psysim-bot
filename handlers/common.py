from uuid import uuid4
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_user, create_user, get_user_by_id, get_user_by_referral_code
)
from keyboards.builder import main_menu
from states import MainMenu
from texts.common import get_start_text
from config import logger

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession):
    from_user = message.from_user
    logger.debug(from_user)

    text_parts = message.text.split()
    referred_by_id = None

    # Обработка рефералки
    if len(text_parts) > 1 and text_parts[1].startswith("ref_"):
        try:
            referred_by_id = int(text_parts[1].split("_")[1])
            logger.debug(f"Referral detected! Invited by {referred_by_id}")
        except (IndexError, ValueError):
            logger.warning("Failed to parse referral code")

    db_user = await get_user(session, telegram_id=from_user.id)

    if db_user is None:
        referral_code = str(uuid4())[:8]
        db_user = await create_user(
            session=session,
            telegram_id=from_user.id,
            username=from_user.username,
            language_code=from_user.language_code,
            is_premium=from_user.is_premium,
            referred_by_id=referred_by_id,
            referral_code=referral_code,
        )
        logger.debug(f"User is new! created referal code {referral_code}")
    else:
        logger.debug(f"User exists: {db_user}")

    if db_user.is_new:
        db_user.is_new = False
        await session.commit()

    text = get_start_text(db_user.is_new)
    await message.answer(text, reply_markup=main_menu())
    await state.set_state(MainMenu.choosing)

@router.callback_query(lambda c: c.data == "back_main")
async def back_to_main_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔙 Возврат в главное меню", 
        reply_markup=main_menu()
    )
    await state.set_state(MainMenu.choosing)