from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user
from keyboards.builder import main_menu
from states import MainMenu
from texts.common import get_start_text, BACK_TO_MENU_TEXT
from config import logger
from services.referral_manager import (
    process_referral_code,
    create_new_user_with_referral,
    handle_referral_bonus
)

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        from_user = message.from_user
        logger.debug(f"Start command from: {from_user.id}")

        text_parts = message.text.split()
        referrer = None

        # Проверка реферального кода
        if len(text_parts) > 1 and text_parts[1].startswith("ref_"):
            referral_code = text_parts[1].split("_")[1]
            referrer = await process_referral_code(session, referral_code)

        # Получаем или создаем пользователя
        db_user = await get_user(session, telegram_id=from_user.id)
        is_new_user = False

        if db_user is None:
            db_user = await create_new_user_with_referral(session, from_user, referrer)
            is_new_user = True

            if referrer:
                await handle_referral_bonus(session, db_user, referrer, message.bot)
        else:
            logger.debug(f"User already exists: {db_user.id}")
            is_new_user = db_user.is_new
            if is_new_user:
                db_user.is_new = False
                await session.commit()

        # Отправка приветственного текста
        text = get_start_text(is_new_user)
        await message.answer(text, reply_markup=main_menu())
        await state.set_state(MainMenu.choosing)

    except Exception as e:
        logger.error(f"Error in cmd_start: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при обработке команды")
        await state.set_state(MainMenu.choosing)
    finally:
        await session.close()


@router.callback_query(lambda c: c.data == "back_main")
async def back_to_main_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        BACK_TO_MENU_TEXT,
        reply_markup=main_menu()
    )
    await state.set_state(MainMenu.choosing)
