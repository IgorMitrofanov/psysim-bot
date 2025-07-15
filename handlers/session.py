from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from states import MainMenu
from keyboards.builder import (
    free_session_resistance_menu,
    free_session_emotion_menu,
    free_session_format_menu,
    free_session_confirm_menu,
    main_menu
)

router = Router()

@router.callback_query(MainMenu.free_session_resistance)
async def free_session_resistance_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["resistance_medium", "resistance_high"]:
        await state.update_data(resistance=callback.data)
        await callback.message.edit_text(
            "💥 Выбор эмоционального состояния клиента", 
            reply_markup=free_session_emotion_menu()
        )
        await state.set_state(MainMenu.free_session_emotion)
    elif callback.data == "back_main":
        await callback.message.edit_text(
            "🔙 Возврат в главное меню", 
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)

@router.callback_query(MainMenu.free_session_emotion)
async def free_session_emotion_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data.startswith("emotion_"):
        await state.update_data(emotion=callback.data)
        await callback.message.edit_text(
            "Выбери формат общения:", 
            reply_markup=free_session_format_menu()
        )
        await state.set_state(MainMenu.free_session_format)
    elif callback.data == "back_to_resistance":
        await callback.message.edit_text(
            "🧱 Выбор сопротивления клиента", 
            reply_markup=free_session_resistance_menu()
        )
        await state.set_state(MainMenu.free_session_resistance)

@router.callback_query(MainMenu.free_session_format)
async def free_session_format_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["format_text", "format_audio"]:
        await state.update_data(format=callback.data)
        await callback.message.edit_text(
            "Готов(а) начать сессию с ИИ-клиентом?\n\n"
            "⏱ У тебя есть 20 минут на сессию.\n"
            "📝 По её завершении автоматически придёт супервизорский отчёт.\n"
            "❗ Если хочешь закончить раньше — нажми «🔚 Завершить сессию». Отчёт при этом не отправится.",
            reply_markup=free_session_confirm_menu()
        )
        await state.set_state(MainMenu.free_session_confirm)
    elif callback.data == "back_to_emotion":
        await callback.message.edit_text(
            "💥 Выбор эмоционального состояния клиента", 
            reply_markup=free_session_emotion_menu()
        )
        await state.set_state(MainMenu.free_session_emotion)

@router.callback_query(MainMenu.free_session_confirm)
async def free_session_confirm_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "start_free_session":
        data = await state.get_data()
        await callback.message.edit_text(
            f"Сессия началась!\n\n"
            f"Сопротивление: {data.get('resistance')}\n"
            f"Эмоция: {data.get('emotion')}\n"
            f"Формат: {data.get('format')}\n\n"
            "Удачи! 🎉"
        )
    elif callback.data == "end_free_session":
        await callback.message.edit_text("Сессия завершена досрочно. Отчёт не будет отправлен.")
        await state.clear()
        await callback.message.answer(
            "Возврат в главное меню", 
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)
    elif callback.data == "back_main":
        await callback.message.edit_text(
            "🔙 Возврат в главное меню", 
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)