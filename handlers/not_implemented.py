from aiogram import Router, types


router = Router(name="not_implemented")

@router.callback_query(lambda c: c.data == "not_implemented")
async def not_implemented_handler(callback: types.CallbackQuery):
    await callback.answer("Функция пока недоступна ❌", show_alert=True)