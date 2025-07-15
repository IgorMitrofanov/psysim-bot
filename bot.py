import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy import select
import datetime
from aiogram.filters import Command

from dotenv import load_dotenv
import os

load_dotenv()

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Config ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot_db.sqlite")
AI_API_KEY = os.getenv("AI_API_KEY")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL")
SESSION_LENGTH_MINUTES = os.getenv("SESSION_LENGTH_MINUTES")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    

# --- Logging ---
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


# --- Bot Setup ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- SQLAlchemy Setup ---
Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# --- Models ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String)
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_new = Column(Boolean, default=True)
    active_tariff = Column(String, default="trial")
    tariff_expires = Column(DateTime)
    
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    description = Column(String)
    price = Column(Integer)
    
    # to do sessions (bot msg history, user msg history, res_lvl, emotion) achivments, relations on DB

# --- States ---
class MainMenu(StatesGroup):
    choosing = State()
    feedback = State()
    suggestion = State()
    error_report = State()
    free_session_resistance = State()
    free_session_emotion = State()
    free_session_format = State()
    free_session_confirm = State()

# --- UI Builders ---
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Начать сессию", callback_data="start_session")],
        [InlineKeyboardButton(text="📊 Мои сессии и отчёты", callback_data="my_sessions")],
        [InlineKeyboardButton(text="👤 Мой профиль и покупки", callback_data="profile")],
        [InlineKeyboardButton(text="📚 Помощь", callback_data="help")],
        [InlineKeyboardButton(text="💬 Отзывы и предложения", callback_data="feedback_menu")],
        [InlineKeyboardButton(text="🤝 Партнерская пограмма", callback_data="referral")],
        [InlineKeyboardButton(text="🎯 Мои цели", callback_data="goals")],
        [InlineKeyboardButton(text="🏅 Мои достижения", callback_data="achievements")],
    ])

def feedback_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data="leave_feedback")],
        [InlineKeyboardButton(text="📌 Предложить улучшение", callback_data="suggest_feature")],
        [InlineKeyboardButton(text="⚠️ Сообщить об ошибке", callback_data="report_error")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")],
    ])
    
def cancel_feedback_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_feedback")]
    ])

def free_session_resistance_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Среднее", callback_data="resistance_medium")],
        [InlineKeyboardButton(text="🔴 Высокое", callback_data="resistance_high")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])

def free_session_emotion_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😢 Тревожный и ранимый", callback_data="emotion_anxious")],
        [InlineKeyboardButton(text="😡 Агрессивно настроенный", callback_data="emotion_aggressive")],
        [InlineKeyboardButton(text="🧊 Холодный, отстранённый", callback_data="emotion_cold")],
        [InlineKeyboardButton(text="😶 Закрытый, в шоке", callback_data="emotion_shocked")],
        [InlineKeyboardButton(text="😭 На грани срыва", callback_data="emotion_breakdown")],
        [InlineKeyboardButton(text="🙃 Поверхностно весёлый, избегает тем", callback_data="emotion_superficial")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_resistance")]
    ])

def free_session_format_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Текст", callback_data="format_text")],
        [InlineKeyboardButton(text="🎧 Аудио", callback_data="format_audio")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_emotion")]
    ])

def free_session_confirm_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟣 Начать сессию", callback_data="start_free_session")],
        [InlineKeyboardButton(text="🔚 Завершить сессию", callback_data="end_free_session")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])

def profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Продлить подписку", callback_data="extend_subscription")],
        [InlineKeyboardButton(text="📦 Купить пакет сессий", callback_data="buy_sessions")],
        [InlineKeyboardButton(text="🧾 Посмотреть тарифы", callback_data="view_tariffs")],
        [InlineKeyboardButton(text="📊 Мои сессии и отчёты", callback_data="my_sessions")],
        [InlineKeyboardButton(text="💬 Связаться с поддержкой", callback_data="support_contact")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")],
    ])

def profile_text(user_data: dict):
    return (
        f"👤 Твой профиль\n"
        f"👥 Имя пользователя: @{user_data.get('username', 'unknown')}\n"
        f"🆔 ID: {user_data.get('telegram_id', 'unknown')}\n"
        f"📅 Дата регистрации: {user_data.get('registered_at', 'unknown')}\n"
        f"🎯 Активный тариф: {user_data.get('active_tariff', 'trial')}\n\n"
        f"📆 Действует до: {user_data.get('tariff_expires', '—')}\n"
        f"📈 Пройдено сессий: {user_data.get('sessions_done', 0)}\n"
        f"🧠 Последний сценарий: {user_data.get('last_scenario', '—')}\n\n"
        f"💳 Мои покупки\n"
        f"Бонус от рефералов: \n\n"
        f"🛍 Последние заказы:\n"
        f"• 10.06 — Подписка \"Безлимит 30 дней\" — 2490 ₽\n"
        f"• 21.05 — Пакет \"3 сессии\" — 590 ₽\n"
        f"• 10.05 — Пробная сессия — 0 ₽\n\n"
    )

def referral_text():
    return (
        "🎉 Приглашай коллег — получай бонусы!\n\n"
        "Ты можешь делиться своей реферальной ссылкой. За каждую оплачивающую подписку по твоей ссылке ты получаешь:\n\n"
        "🎧 1 бесплатную сессию в подарок\n"
        "или\n"
        "💸 Скидку 10% на следующую подписку\n\n"
        "👥 Приглашённых: 3\n"
        "💰 Бонусов накоплено: 1 бесплатная сессия\n\n"
        "📎 Твоя ссылка:\n"
        "https://t.me/your_bot_name?start=ref_123456\n\n"
        "👇 Что хочешь сделать?"
    )

def referral_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Скопировать ссылку", callback_data="copy_referral_link")],
        [InlineKeyboardButton(text="📊 Мои приглашённые", callback_data="my_referrals")],
        [InlineKeyboardButton(text="❓ Как это работает", callback_data="how_referral_works")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_main")],
    ])
    
# --- Help Texts ---
HELP_MAIN_TEXT = (
    "📚 <b>Помощь / Как пользоваться</b>\n\n"
    "Выбери, что тебя интересует 👇"
)

HELP_START_SESSION_TEXT = (
    "🧭 <b>Как начать сессию</b>\n\n"
    "1️⃣ Нажми «Начать сессию» в меню\n"
    "2️⃣ Выбери тематику клиента\n"
    "3️⃣ Укажи уровень сопротивления (или выбери «рандом»)\n"
    "4️⃣ Выбери формат общения: 📝 текст или 🎧 аудио\n"
    "5️⃣ Веди сессию 20 минут\n\n"
    "После завершения — получишь супервизорский отчёт.\n\n"
)

HELP_AFTER_SESSION_TEXT = (
    "📄 <b>После сессии ты получишь:</b>\n\n"
    "– 🧠 Отчёт от ИИ-супервизора\n"
    "– 💬 Комментарии: что получилось и что улучшить\n"
    "– 📈 Рекомендации\n"
    "– 📊 Ежемесячную сводку (если подписка)\n\n"
    "💡 Это поможет тебе расти как психологу в безопасной среде.\n\n"
)

HELP_FAQ_TEXT = (
    "💡 <b>FAQ — Часто задаваемые вопросы</b>\n\n"
    "❓ <b>Можно ли пользоваться без подписки?</b>\n"
    "✅ Да! Доступна 1 бесплатная сессия. Потом — подписка или пакет.\n\n"
    "❓ <b>Чем бот отличается от ChatGPT?</b>\n"
    "🤖 Все сценарии здесь созданы психологами, а поведение ИИ-клиента реалистично, с учётом сопротивления, эмоций и терапевтической логики.\n\n"
    "❓ <b>Заменяет ли это супервизию?</b>\n"
    "🧠 Нет, это тренировочный инструмент. Но он поможет тебе подготовиться к практике и лучше себя понимать.\n\n"
)

def help_detail_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔘 Как начать сессию", callback_data="help_start_session")],
        [InlineKeyboardButton(text="📄 Что происходит после сессии", callback_data="help_after_session")],
        [InlineKeyboardButton(text="💡 Часто задаваемые вопросы", callback_data="help_faq")],
        [InlineKeyboardButton(text="📞 Связаться с поддержкой", callback_data="support_contact")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])

def help_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="help")]
    ])

def back_to_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")]
    ])

# --- Handlers ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(stmt)
        db_user = result.scalar_one_or_none()
        if not db_user:
            db_user = User(telegram_id=message.from_user.id, username=message.from_user.username)
            session.add(db_user)
            await session.commit()
        if db_user.is_new:
            text = (
                "👋 Привет! Рада приветствовать тебя в AI-тренажёре для психологов.\n\n"
                "Я — практикующий психолог и хорошо знаю, как сложно бывает начать практику: первый клиент, страх навредить, растерянность перед сопротивлением. Этот проект создан, чтобы помочь тебе безопасно и эффективно отработать навыки консультирования.\n\n"
                "🧠 Здесь ты сможешь:\n"
                "– потренироваться в живом диалоге с ИИ-клиентом,\n"
                "– выбрать уровень сложности и тему запроса,\n"
                "– получать супервизорский отчёт после каждой сессии — с разбором, что было хорошо, а где можно было поступить иначе.\n\n"
                "🤔 Почему не просто ChatGPT? У нас — реализм, сопротивление, сценарии и эмоции.\n\n"
                "🎁 Доступна бесплатная тестовая сессия. Начнем?"
            )
            db_user.is_new = False
            await session.commit()
        else:
            text = (
                "👋 Привет! Рада видеть тебя снова в тренажёре 🌱\n\n"
                "Ты можешь:\n"
                "🔹 Начать новую сессию\n"
                "🔹 Посмотреть прошлые отчёты\n"
                "🔹 Отслеживать свой прогресс\n"
                "🔹 Изучить рекомендации по улучшению\n\n"
                "Готов(а) к новой практике?"
            )
    await message.answer(text, reply_markup=main_menu())
    await state.set_state(MainMenu.choosing)

# --- Help submenu ---

@dp.callback_query(lambda c: c.data.startswith("help"))
async def help_pages_handler(callback: types.CallbackQuery):
    await callback.answer()
    match callback.data:
        case "help":
            await callback.message.edit_text(HELP_MAIN_TEXT, reply_markup=help_detail_keyboard())
        case "help_start_session":
            await callback.message.edit_text(HELP_START_SESSION_TEXT, reply_markup=help_back_keyboard())
        case "help_after_session":
            await callback.message.edit_text(HELP_AFTER_SESSION_TEXT, reply_markup=help_back_keyboard())
        case "help_faq":
            await callback.message.edit_text(HELP_FAQ_TEXT, reply_markup=help_back_keyboard())
        case "help_how_to" | "help_supervision" | "help_client_choice" | "help_payment":
            await callback.message.edit_text("🔧 Этот раздел ещё в разработке. Следи за обновлениями!", reply_markup=help_back_keyboard())

    
@dp.callback_query(lambda c: c.data == "cancel_feedback")
async def cancel_feedback_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("❌ Отменено")
    await callback.message.edit_text("🔙 Возврат в главное меню", reply_markup=main_menu())
    await state.set_state(MainMenu.choosing)
    
async def acknowledge_user_feedback(
    message: types.Message,
    state: FSMContext,
    success_text: str
):
    data = await state.get_data()
    msg_id = data.get("feedback_msg_id")
    try:
        if msg_id:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text=success_text,
                reply_markup=back_to_main_keyboard()
            )
        await asyncio.sleep(1.5)
        await message.delete()  # Удаляем текстовое сообщение от пользователя
    except Exception as e:
        logging.warning(f"Ошибка при acknowledge: {e}")
    await state.set_state(MainMenu.choosing)    

@dp.message(MainMenu.feedback)
async def handle_feedback(message: types.Message, state: FSMContext):
    await acknowledge_user_feedback(
        message, state,
        "✅ Спасибо за твой отзыв! Он уже отправлен нашей команде 💛"
    )

@dp.message(MainMenu.suggestion)
async def handle_suggestion(message: types.Message, state: FSMContext):
    await acknowledge_user_feedback(
        message, state,
        "🧠 Отличная идея! Мы обязательно её рассмотрим 💫"
    )

@dp.message(MainMenu.error_report)
async def handle_error(message: types.Message, state: FSMContext):
    await acknowledge_user_feedback(
        message, state,
        "🚑 Ошибка зафиксирована. Спасибо, что сообщил(а)."
    )
    
@dp.callback_query(MainMenu.choosing)
async def handle_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    match callback.data:
        case "start_session":
            await callback.message.edit_text("🧱 Выбор сопротивления клиента", reply_markup=free_session_resistance_menu())
            await state.set_state(MainMenu.free_session_resistance)
        case "profile":
            async with async_session() as session:
                # Здесь для примера подставляем статичные данные
                user_data = {
                    "username": callback.from_user.username or "unknown",
                    "telegram_id": callback.from_user.id,
                    "registered_at": "10 мая 2025",
                    "active_tariff": "Подписка \"Безлимит на 30 дней\"",
                    "tariff_expires": "17 июля 2025",
                    "sessions_done": 14,
                    "last_scenario": "Границы / Высокое сопротивление",
                }
            await callback.message.edit_text(profile_text(user_data), reply_markup=profile_keyboard())
        case "referral":
            await callback.message.edit_text(referral_text(), reply_markup=referral_keyboard())
        case "feedback_menu":
            await callback.message.edit_text("💬 Отзывы и предложения\n\n🗣 Нам очень важно твоё мнение!\nВыбери, что хочешь сделать:", reply_markup=feedback_menu())
        case "leave_feedback":
            await callback.message.edit_text(
                "✍️ Напиши отзыв в ответ на это сообщение или нажми «🔙 Отмена»:",
                reply_markup=cancel_feedback_keyboard()
            )
            await state.update_data(feedback_msg_id=callback.message.message_id)
            await state.set_state(MainMenu.feedback)

        case "suggest_feature":
            await callback.message.edit_text(
                "💡 Напиши предложение по улучшению или нажми «🔙 Отмена»:",
                reply_markup=cancel_feedback_keyboard()
            )
            await state.update_data(feedback_msg_id=callback.message.message_id)
            await state.set_state(MainMenu.suggestion)

        case "report_error":
            await callback.message.edit_text(
                "⚠️ Опиши ошибку или нажми «🔙 Отмена»:",
                reply_markup=cancel_feedback_keyboard()
            )
            await state.update_data(feedback_msg_id=callback.message.message_id)
            await state.set_state(MainMenu.error_report)
        case "back_main":
            await callback.message.edit_text("🔙 Возврат в главное меню", reply_markup=main_menu())
            await state.set_state(MainMenu.choosing)
        case "help":
            await callback.message.edit_text(HELP_MAIN_TEXT, reply_markup=help_detail_keyboard())
        case _:
            await callback.message.edit_text(f"🔧 Заглушка: {callback.data}\n(Функция пока в разработке)", reply_markup=main_menu())

# --- Free session flow ---

@dp.callback_query(MainMenu.free_session_resistance)
async def free_session_resistance_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["resistance_medium", "resistance_high"]:
        await state.update_data(resistance=callback.data)
        await callback.message.edit_text("💥 Выбор эмоционального состояния клиента", reply_markup=free_session_emotion_menu())
        await state.set_state(MainMenu.free_session_emotion)
    elif callback.data == "back_main":
        await callback.message.edit_text("🔙 Возврат в главное меню", reply_markup=main_menu())
        await state.set_state(MainMenu.choosing)

@dp.callback_query(MainMenu.free_session_emotion)
async def free_session_emotion_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data.startswith("emotion_"):
        await state.update_data(emotion=callback.data)
        await callback.message.edit_text("Выбери формат общения:", reply_markup=free_session_format_menu())
        await state.set_state(MainMenu.free_session_format)
    elif callback.data == "back_to_resistance":
        await callback.message.edit_text("🧱 Выбор сопротивления клиента", reply_markup=free_session_resistance_menu())
        await state.set_state(MainMenu.free_session_resistance)

@dp.callback_query(MainMenu.free_session_format)
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
        await callback.message.edit_text("💥 Выбор эмоционального состояния клиента", reply_markup=free_session_emotion_menu())
        await state.set_state(MainMenu.free_session_emotion)

@dp.callback_query(MainMenu.free_session_confirm)
async def free_session_confirm_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "start_free_session":
        data = await state.get_data()
        # Запуск сессии по параметрам из data, заглушка:
        await callback.message.edit_text(
            f"Сессия началась!\n\n"
            f"Сопротивление: {data.get('resistance')}\n"
            f"Эмоция: {data.get('emotion')}\n"
            f"Формат: {data.get('format')}\n\n"
            "Удачи! 🎉"
        )
        # Здесь можно перейти в следующее состояние сессии
    elif callback.data == "end_free_session":
        await callback.message.edit_text("Сессия завершена досрочно. Отчёт не будет отправлен.")
        await state.clear()
        await callback.message.answer("Возврат в главное меню", reply_markup=main_menu())
        await state.set_state(MainMenu.choosing)
    elif callback.data == "back_main":
        await callback.message.edit_text("🔙 Возврат в главное меню", reply_markup=main_menu())
        await state.set_state(MainMenu.choosing)

# --- Feedback, suggestion and error handling messages ---
@dp.message(MainMenu.feedback)
async def handle_feedback(message: types.Message, state: FSMContext):
    await message.answer("✅ Спасибо за твой отзыв! Он уже отправлен нашей команде 💛")
    await state.set_state(MainMenu.choosing)

@dp.message(MainMenu.suggestion)
async def handle_suggestion(message: types.Message, state: FSMContext):
    await message.answer("🧠 Отличная идея! Мы обязательно её рассмотрим 💫")
    await state.set_state(MainMenu.choosing)

@dp.message(MainMenu.error_report)
async def handle_error(message: types.Message, state: FSMContext):
    await message.answer("🚑 Ошибка зафиксирована. Спасибо, что сообщил(а).")
    await state.set_state(MainMenu.choosing)

# --- Referral submenu ---
@dp.callback_query(lambda c: c.data in ["copy_referral_link", "my_referrals", "how_referral_works"])
async def referral_submenu_handler(callback: types.CallbackQuery):
    texts = {
        "copy_referral_link": "📎 Ссылка скопирована в буфер обмена (заглушка).",
        "my_referrals": "📊 Список приглашённых (заглушка).",
        "how_referral_works": "❓ Пояснение, как работает партнёрка (заглушка).",
    }
    await callback.answer(texts[callback.data], show_alert=True)

# --- DB Init ---
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# --- Entry Point ---
async def main():
    logging.info("🚀 Бот запускается...")
    await init_db()
    try:
        await dp.start_polling(bot)
    finally:
        logging.info("🛑 Бот остановлен.")

if __name__ == "__main__":
    asyncio.run(main())
