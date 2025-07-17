from functools import wraps
from datetime import datetime, timedelta
from config import config
from aiogram import types
from states import MainMenu
from keyboards.builder import main_menu

def check_session_timeout():
    def decorator(func):
        @wraps(func)
        async def wrapper(event: types.Message | types.CallbackQuery, state, *args, **kwargs):
            data = await state.get_data()
            start_str = data.get("session_start")

            if start_str:
                start_time = datetime.fromisoformat(start_str)
                session_length_minutes = int(config.SESSION_LENGTH_MINUTES or 5)
                if datetime.utcnow() - start_time > timedelta(minutes=session_length_minutes):
                    if isinstance(event, types.CallbackQuery):
                        await event.message.edit_text("⌛️ Время сессии истекло.")
                        await event.message.answer("🔙 Возврат в меню", reply_markup=main_menu())
                    else:
                        await event.answer("⌛️ Время сессии истекло.")
                        await event.answer("🔙 Возврат в меню", reply_markup=main_menu())

                    await state.clear()
                    await state.set_state(MainMenu.choosing)
                    return
            return await func(event, state, *args, **kwargs)
        return wrapper
    return decorator
