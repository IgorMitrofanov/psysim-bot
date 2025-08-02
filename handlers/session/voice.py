from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from states import MainMenu
from services.session_manager import SessionManager
from services.speech_to_text import transcribe_voice
from database.crud import get_user
from database.models import TariffType   
import os
from uuid import uuid4
from aiogram.types import Message


from handlers.session.interaction import session_interaction_handler

from config import logger

router = Router(name="session_voice")

@router.message(MainMenu.in_session, F.voice)
async def handle_voice_message(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager,
    bot
):
    """
    Обрабатывает голосовые сообщения в активной сессии.
    
    Проверяет, есть ли у пользователя активный тариф, и распознает голосовое сообщение.
    Если тариф PRO или UNLIMITED, то распознает голос и отправляет текст в обработчик сессии.
    Если тариф неактивен, отправляет сообщение об ошибке.
    """
    user_data = await get_user(session, telegram_id=message.from_user.id)
    
    if not user_data:
        await message.answer("Ошибка: пользователь не найден.")
        return

    # Проверка тарифа
    if user_data.active_tariff in [TariffType.PRO, TariffType.UNLIMITED]:
        try:
            # Получаем файл с сервера Telegram
            file_info = await bot.get_file(message.voice.file_id)
            
            # Создать папку если ее нет
            if not os.path.exists("./tmp"):
                os.makedirs("./tmp")

            # Уникальное имя временного файла
            tmp_path = f"./tmp/{uuid4().hex}.ogg"

            # Скачиваем файл
            await bot.download_file(file_info.file_path, tmp_path)

            # Распознаём голос
            text = await transcribe_voice(tmp_path)

            os.remove(tmp_path)  # Удаляем временный файл

            if not text.strip():
                await message.answer("Не удалось распознать голосовое сообщение.")
                return

            # Создаём фейковое текстовое сообщение
            fake_text_message = Message(
                message_id=message.message_id,
                date=message.date,
                chat=message.chat,
                from_user=message.from_user,
                message_thread_id=message.message_thread_id,
                text=text)
        
            await session_interaction_handler(fake_text_message, state, session, session_manager, bot=message.bot)

        except Exception as e:
            logger.error(f"Error during voice processing: {e}")
            await message.answer("Произошла ошибка при обработке голосового сообщения.")
    else:
        await message.answer(
            "<b>Голосовые сообщения доступны только по тарифам PRO и UNLIMITED.</b>\n\n"
            "Пожалуйста, обновите подписку, чтобы пользоваться этой функцией."
        )