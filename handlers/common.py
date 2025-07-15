from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import get_or_create_user
from keyboards.builder import main_menu
from states import MainMenu
from texts.common import get_start_text

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession):
    db_user = await get_or_create_user(
        session=session,
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )

    text = get_start_text(db_user.is_new)
    if db_user.is_new:
        db_user.is_new = False
        await session.commit()

    await message.answer(text, reply_markup=main_menu())
    await state.set_state(MainMenu.choosing)

@router.callback_query(lambda c: c.data == "back_main")
async def back_to_main_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔙 Возврат в главное меню", 
        reply_markup=main_menu()
    )
    await state.set_state(MainMenu.choosing)