from aiogram import Router, types, Bot
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user
from database.models import TariffType
from keyboards.builder import subscription_keyboard
from keyboards.builder import profile_keyboard
from texts.subscription_texts import (
    TARIFF_MENU_TEXT,
    TARIFF_SUCCESS_TEMPLATE,
    TARIFF_FAIL_FUNDS,
    TARIFF_USER_NOT_FOUND,
    UNKNOWN_TARIFF
)
from config import config, logger
import datetime
from database.models import Order
from services.referral_manager import process_referral_bonus_after_payment

router = Router(name="subscription")


@router.callback_query(lambda c: c.data == "buy")
async def buy_tariff_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        TARIFF_MENU_TEXT,
        reply_markup=subscription_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data.startswith("activate_"))
async def activate_tariff_callback(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
     # callback.data: activate_start, activate_pro, activate_unlimited
    key = callback.data.removeprefix("activate_")
    if key not in config.TARIFF_MAP:
        await callback.answer(UNKNOWN_TARIFF, show_alert=True)
        return
    
    tariff_name, cost, days, _ = config.TARIFF_MAP[key]
    
    # Получаем соответствующий enum-объект
    try:
        tariff_enum = TariffType[key.upper()]
    except KeyError:
        await callback.answer(UNKNOWN_TARIFF, show_alert=True)
        return

    user = await get_user(session, telegram_id=callback.from_user.id)
    if not user:
        await callback.answer(TARIFF_USER_NOT_FOUND, show_alert=True)
        return

    if user.balance < cost:
        await callback.answer(TARIFF_FAIL_FUNDS, show_alert=True)
        return

    # Списываем баланс и обновляем тариф
    user.balance -= cost
    user.active_tariff = tariff_enum  # Используем enum вместо строки
    user.tariff_expires = datetime.datetime.utcnow() + datetime.timedelta(days=days)

    # Создаём запись о заказе
    order_description = f"Покупка тарифа «{tariff_name}» на {days} дней"
    order = Order(
        user_id=user.id,
        description=order_description,
        price=cost,
        date=datetime.datetime.utcnow()
    )
    session.add(order)

    await process_referral_bonus_after_payment(session, user.id, bot)

    await session.commit()

    text = TARIFF_SUCCESS_TEMPLATE.format(tariff=tariff_name.capitalize(), days=days, cost=cost)
    # Ответить в чат с профилем и клавиатурой профиля
    await callback.message.edit_text(text, reply_markup=profile_keyboard())
    await callback.answer()
    
    
    
# from utils.payment import generate_sbp_link  # твой модуль
# from database.models import Order
# import uuid

# @router.callback_query(lambda c: c.data.startswith("activate_"))
# async def initiate_payment(callback: types.CallbackQuery, session: AsyncSession):
#     tariff_map = {
#         "activate_start": ("start", 590, 7),
#         "activate_pro": ("pro", 1490, 30),
#         "activate_unlimited": ("unlimited", 2490, 30)
#     }

#     data = callback.data
#     if data not in tariff_map:
#         await callback.answer("❌ Неизвестный тариф", show_alert=True)
#         return

#     tariff_code, cost, days = tariff_map[data]
#     user = await get_user(session, telegram_id=callback.from_user.id)
#     if not user:
#         await callback.answer("❌ Пользователь не найден", show_alert=True)
#         return

#     order_id = str(uuid.uuid4())
#     description = f"Тариф «{tariff_code}» на {days} дней"

#     # Генерация платёжной ссылки/QR
#     payment_url = generate_sbp_link(order_id=order_id, amount=cost, user_id=user.id)

#     # Сохраняем заказ (в ожидании оплаты)
#     order = Order(
#         id=order_id,
#         user_id=user.id,
#         description=description,
#         price=cost
#     )
#     session.add(order)
#     await session.commit()

#     await callback.message.edit_text(
#         f"💳 Для активации подписки оплатите {cost} ₽ по ссылке ниже:\n\n"
#         f"<a href=\"{payment_url}\">{payment_url}</a>\n\n"
#         f"После оплаты подписка активируется автоматически.",
#         parse_mode="HTML"
#     )
#     await callback.answer()


# def generate_sbp_link(order_id: str, amount: int, user_id: int) -> str:
#     return (
#         f"https://pay.example.com/create?"
#         f"order_id={order_id}&amount={amount}&user_id={user_id}"
#     )
    
# @router.post("/webhook/payment")
# async def payment_webhook(
#     request: Request,
#     session: AsyncSession = Depends(get_session)
# ):
#     data = await request.json()

#     order_id = data.get("order_id")
#     status = data.get("status")
#     amount = data.get("amount")
#     telegram_id = data.get("telegram_id")  # Если передаёшь

#     # 1. Найти заказ
#     stmt = select(Order).where(Order.id == order_id)
#     result = await session.execute(stmt)
#     order = result.scalar_one_or_none()

#     if not order:
#         return {"ok": False, "error": "Order not found"}

#     # 2. Проверить и обновить
#     if status == "success" and order.status != "paid":
#         order.status = "paid"

#         # 3. Обновляем тариф пользователя
#         user = await session.get(User, order.user_id)
#         if user:
#             # Определяем тариф по description
#             if "start" in order.description.lower():
#                 user.active_tariff = "start"
#                 user.tariff_expires = datetime.datetime.utcnow() + datetime.timedelta(days=7)
#             elif "pro" in order.description.lower():
#                 user.active_tariff = "pro"
#                 user.tariff_expires = datetime.datetime.utcnow() + datetime.timedelta(days=30)
#             elif "unlimited" in order.description.lower():
#                 user.active_tariff = "unlimited"
#                 user.tariff_expires = datetime.datetime.utcnow() + datetime.timedelta(days=30)

#             # 4. Уведомляем пользователя в Telegram
#             try:
#                 await bot.send_message(
#                     chat_id=user.telegram_id,
#                     text=f"✅ Платёж получен!\nПодписка «{user.active_tariff.capitalize()}» активирована."
#                 )
#             except Exception as e:
#                 print(f"Ошибка при отправке уведомления: {e}")

#     await session.commit()
#     return {"ok": True}