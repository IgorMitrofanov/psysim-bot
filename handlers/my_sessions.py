from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.crud import get_user, count_user_sessions
from keyboards.builder import profile_keyboard, referral_keyboard
from texts.common import profile_text, referral_text, referral_stats_text
from config import logger
from keyboards.builder import main_menu
from database.models import Session
from database.crud import get_user_sessions
from keyboards.builder import profile_keyboard, sessions_keyboard, session_details_keyboard
from texts.common import SESSIONS_LIST_TITLE, SESSION_DETAILS, NO_SESSIONS_TEXT
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from states import ProfileStates
from sqlalchemy.exc import NoResultFound
import json


from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import Session
from database.crud import get_user, get_user_sessions, count_user_sessions
from keyboards.builder import profile_keyboard, sessions_keyboard, session_details_keyboard
from texts.common import SESSIONS_LIST_TITLE, SESSION_DETAILS, NO_SESSIONS_TEXT, profile_text
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from states import ProfileStates
from sqlalchemy.exc import NoResultFound
import json
import asyncio
from aiogram.exceptions import TelegramBadRequest
from config import logger

router = Router(name="my_sessions")

class MessageManager:
    def __init__(self):
        self.active_messages = {}
    
    async def show_message(self, callback: types.CallbackQuery, text: str, prefix: str = ""):
        """Показывает новое сообщение, удаляя все предыдущие"""
        chat_id = callback.message.chat.id
        await self.clear_messages(callback.bot, chat_id)
        
        full_text = f"{prefix}\n\n{text}" if prefix else text
        messages = []
        
        if len(full_text) <= 4000:
            msg = await callback.message.answer(full_text)
            messages.append(msg.message_id)
        else:
            header_msg = await callback.message.answer(prefix if prefix else "Сообщение:")
            messages.append(header_msg.message_id)
            
            for i in range(0, len(text), 4000):
                part_msg = await callback.message.answer(text[i:i+4000])
                messages.append(part_msg.message_id)
        
        self.active_messages[chat_id] = messages
    
    async def clear_messages(self, bot, chat_id):
        """Удаляет все активные сообщения для указанного чата"""
        if chat_id in self.active_messages:
            for msg_id in self.active_messages[chat_id]:
                try:
                    await bot.delete_message(chat_id, msg_id)
                except TelegramBadRequest as e:
                    if "message to delete not found" not in str(e):
                        logger.error(f"Error deleting message: {e}")
            del self.active_messages[chat_id]

msg_manager = MessageManager()

@router.callback_query(F.data == "my_sessions")
async def show_sessions_list(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.answer("Пользователь не найден")
        return
    
    sessions = await get_user_sessions(session, db_user.id)
    
    if not sessions:
        await callback.message.edit_text(
            NO_SESSIONS_TEXT,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_profile")]
            ])
        )
        return
    
    await state.set_state(ProfileStates.viewing_sessions)
    await state.update_data({
        "sessions_page": 0,
        "user_id": db_user.id
    })
    
    await callback.message.edit_text(
        SESSIONS_LIST_TITLE,
        reply_markup=sessions_keyboard(sessions, page=0)
    )

@router.callback_query(F.data.startswith("sessions_page_"), ProfileStates.viewing_sessions)
async def paginate_sessions(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await callback.answer("Ошибка: пользователь не найден")
        return
    
    page = int(callback.data.split("_")[-1])
    sessions = await get_user_sessions(session, user_id)
    
    await state.update_data(sessions_page=page)
    await callback.message.edit_reply_markup(
        reply_markup=sessions_keyboard(sessions, page=page)
    )

@router.callback_query(F.data.startswith("session_detail_"), ProfileStates.viewing_sessions)
async def show_session_details(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    session_id = int(callback.data.split("_")[-1])
    try:
        session_obj = await session.get(Session, session_id)
        if not session_obj:
            raise NoResultFound
        
        text = SESSION_DETAILS.format(
            persona_name=session_obj.persona_name or "Не указан",
            emotional=session_obj.emotional or "Не указан",
            resistance=session_obj.resistance_level or "Не указан",
            started_at=session_obj.started_at.strftime('%d.%m.%Y %H:%M'),
            ended_at=session_obj.ended_at.strftime('%d.%m.%Y %H:%M') if session_obj.ended_at else "Не завершена"
        )
        
        await state.set_state(ProfileStates.viewing_session_details)
        await state.update_data(current_session_id=session_id)
        
        await callback.message.edit_text(
            text,
            reply_markup=session_details_keyboard(session_id)
        )
    except NoResultFound:
        await callback.answer("Сессия не найдена", show_alert=True)
        await back_to_sessions_list(callback, session, state)

@router.callback_query(F.data.startswith("show_user_messages_"), ProfileStates.viewing_session_details)
async def show_user_messages(callback: types.CallbackQuery, session: AsyncSession):
    try:
        session_id = int(callback.data.split("_")[-1])
        stmt = select(Session.user_messages).where(Session.id == session_id)
        result = await session.execute(stmt)
        messages_data = result.scalar_one_or_none()
        
        if not messages_data:
            await callback.answer("✉️ В этой сессии нет ваших сообщений", show_alert=True)
            return
            
        try:
            messages = json.loads(messages_data) if isinstance(messages_data, str) else messages_data
            if not isinstance(messages, list):
                raise ValueError("Сообщения не в формате списка")
                
            filtered_messages = [msg.strip() for msg in messages if msg and str(msg).strip()]
            formatted_messages = "\n".join(f"{i+1}. {msg}" for i, msg in enumerate(filtered_messages))
            
            if not formatted_messages:
                await callback.answer("✉️ Нет доступных сообщений для отображения", show_alert=True)
                return
                
            await msg_manager.show_message(
                callback,
                formatted_messages,
                "📩 Ваши сообщения в этой сессии:"
            )
            await callback.answer()
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing messages: {e}")
            await callback.answer("⚠️ Ошибка формата сообщений", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error showing user messages: {e}")
        await callback.answer("⚠️ Ошибка при получении сообщений", show_alert=True)

@router.callback_query(F.data.startswith("show_bot_messages_"), ProfileStates.viewing_session_details)
async def show_bot_messages(callback: types.CallbackQuery, session: AsyncSession):
    try:
        session_id = int(callback.data.split("_")[-1])
        stmt = select(Session.bot_messages).where(Session.id == session_id)
        result = await session.execute(stmt)
        messages_data = result.scalar_one_or_none()
        
        if not messages_data:
            await callback.answer("🤖 В этой сессии нет ответов бота", show_alert=True)
            return
            
        try:
            messages = json.loads(messages_data) if isinstance(messages_data, str) else messages_data
            if not isinstance(messages, list):
                raise ValueError("Сообщения не в формате списка")
                
            filtered_messages = [msg.strip() for msg in messages if msg and str(msg).strip()]
            formatted_messages = "\n".join(f"{i+1}. {msg}" for i, msg in enumerate(filtered_messages))
            
            if not formatted_messages:
                await callback.answer("🤖 Нет доступных ответов бота", show_alert=True)
                return
                
            await msg_manager.show_message(
                callback,
                formatted_messages,
                "🤖 Ответы бота в этой сессии:"
            )
            await callback.answer()
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing bot messages: {e}")
            await callback.answer("⚠️ Ошибка формата сообщений", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error showing bot messages: {e}")
        await callback.answer("⚠️ Ошибка при получении ответов бота", show_alert=True)

@router.callback_query(F.data.startswith("show_report_"), ProfileStates.viewing_session_details)
async def show_report(callback: types.CallbackQuery, session: AsyncSession):
    try:
        session_id = int(callback.data.split("_")[-1])
        stmt = select(Session.report_text).where(Session.id == session_id)
        result = await session.execute(stmt)
        report_data = result.scalar_one_or_none()
        
        if not report_data:
            await callback.answer("📄 Отчет по этой сессии отсутствует", show_alert=True)
            return
            
        try:
            if isinstance(report_data, str):
                try:
                    report = json.loads(report_data)
                except json.JSONDecodeError:
                    report = report_data
            else:
                report = report_data
                
            if isinstance(report, list):
                filtered_report = [item.strip() for item in report if item and str(item).strip()]
                formatted_report = "\n".join(f"• {item}" for item in filtered_report)
            else:
                formatted_report = str(report).strip()
                
            if not formatted_report:
                await callback.answer("📄 Отчет пуст", show_alert=True)
                return
                
            await msg_manager.show_message(
                callback,
                formatted_report,
                "📄 Отчет по сессии:"
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error parsing report: {e}")
            await callback.answer("⚠️ Ошибка формата отчета", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error showing report: {e}")
        await callback.answer("⚠️ Ошибка при получении отчета", show_alert=True)

@router.callback_query(F.data == "back_to_sessions_list", ProfileStates.viewing_session_details)
async def back_to_sessions_list(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    page = data.get("sessions_page", 0)
    user_id = data.get("user_id")
    
    if not user_id:
        await callback.answer("Ошибка: пользователь не найден")
        return
    
    await msg_manager.clear_messages(callback.bot, callback.message.chat.id)
    
    try:
        await callback.message.delete()
    except TelegramBadRequest as e:
        logger.error(f"Error deleting message: {e}")
    
    sessions = await get_user_sessions(session, user_id)
    
    new_message = await callback.message.answer(
        SESSIONS_LIST_TITLE,
        reply_markup=sessions_keyboard(sessions, page=page)
    )
    
    await state.update_data(list_message_id=new_message.message_id)
    await state.set_state(ProfileStates.viewing_sessions)

@router.callback_query(F.data == "back_profile")
async def back_to_profile(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await msg_manager.clear_messages(callback.bot, callback.message.chat.id)
    await state.clear()
    
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.message.edit_text("Профиль не найден.")
        return
    
    total_sessions = await count_user_sessions(session, db_user.id)
    user_data = {
        "username": db_user.username or "unknown",
        "telegram_id": db_user.telegram_id,
        "registered_at": db_user.registered_at.strftime("%d.%m.%Y"),
        "active_tariff": (
            "Подписка не оформлена" if db_user.active_tariff == "trial"
            else f"Подписка «{db_user.active_tariff}»"
        ),
        "tariff_expires": db_user.tariff_expires.strftime("%d.%m.%Y") if db_user.tariff_expires else "Не указано",
        "sessions_done": total_sessions,
        "bonus_balance": db_user.bonus_balance,
        "balance": db_user.balance,
    }

    await callback.message.edit_text(
        profile_text(user_data),
        reply_markup=profile_keyboard()
    )