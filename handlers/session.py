from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from states import MainMenu
from keyboards.builder import (
    session_resistance_menu,
    session_emotion_menu,
    session_format_menu,
    session_confirm_menu,
    main_menu
)
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import get_user
router = Router(name="session")

@router.callback_query(lambda c: c.data == "start_session")
async def start_session_handler(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.message.edit_text("⚠️ Не удалось загрузить данные пользователя.")
        return

    if db_user.active_tariff == "trial" and db_user.sessions_done >= 1:
        await callback.message.edit_text(
            "🚫 Бесплатных сессий больше нет.\n"
            "Пожалуйста, оформите подписку для продолжения."
        )
        return

    await callback.message.edit_text(
        "🧱 Выбор сопротивления клиента",
        reply_markup=session_resistance_menu()
    )
    await state.set_state(MainMenu.session_resistance)


@router.callback_query(MainMenu.session_resistance)
async def session_resistance_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["resistance_medium", "resistance_high"]:
        await state.update_data(resistance=callback.data)
        await callback.message.edit_text(
            "💥 Выбор эмоционального состояния клиента", 
            reply_markup=session_emotion_menu()
        )
        await state.set_state(MainMenu.session_emotion)
    elif callback.data == "end_session":
        await callback.message.edit_text("Сессия завершена досрочно. Отчёт не будет отправлен.")
        await state.clear()
        await callback.message.answer(
            "Возврат в главное меню",
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)
        return
    elif callback.data == "back_main":
        await callback.message.edit_text(
            "🔙 Возврат в главное меню", 
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)


@router.callback_query(MainMenu.session_emotion)
async def session_emotion_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data.startswith("emotion_"):
        await state.update_data(emotion=callback.data)
        await callback.message.edit_text(
            "Выбери формат общения:", 
            reply_markup=session_format_menu()
        )
        await state.set_state(MainMenu.session_format)
    elif callback.data == "back_to_resistance":
        await callback.message.edit_text(
            "🧱 Выбор сопротивления клиента", 
            reply_markup=session_resistance_menu()
        )
        await state.set_state(MainMenu.session_resistance)


@router.callback_query(MainMenu.session_format)
async def session_format_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["format_text", "format_audio"]:
        await state.update_data(format=callback.data)
        await callback.message.edit_text(
            "Готов(а) начать сессию с ИИ-клиентом?\n\n"
            "⏱ У тебя есть 20 минут на сессию.\n"
            "📝 По её завершении автоматически придёт супервизорский отчёт.\n"
            "❗ Если хочешь закончить раньше — нажми «🔚 Завершить сессию». Отчёт при этом не отправится.",
            reply_markup=session_confirm_menu()
        )
        await state.set_state(MainMenu.session_confirm)
    elif callback.data == "back_to_emotion":
        await callback.message.edit_text(
            "💥 Выбор эмоционального состояния клиента", 
            reply_markup=session_emotion_menu()
        )
        await state.set_state(MainMenu.session_emotion)


@router.callback_query(MainMenu.session_confirm)
async def session_confirm_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    match callback.data:
        case "start_session":
            data = await state.get_data()
            await callback.message.edit_text(
                f"Сессия началась!\n\n"
                f"Сопротивление: {data.get('resistance')}\n"
                f"Эмоция: {data.get('emotion')}\n"
                f"Формат: {data.get('format')}\n\n"
                "Удачи! 🎉"
            )
        case "end_session":
            await callback.message.edit_text("Сессия завершена досрочно. Отчёт не будет отправлен.")
            await state.clear()
            await callback.message.answer(
                "Возврат в главное меню", 
                reply_markup=main_menu()
            )
            await state.set_state(MainMenu.choosing)
        case "back_main":
            await callback.message.edit_text(
                "🔙 Возврат в главное меню", 
                reply_markup=main_menu()
            )
            await state.set_state(MainMenu.choosing)