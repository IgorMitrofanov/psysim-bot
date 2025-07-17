from datetime import datetime, timedelta
from typing import Optional
import asyncio
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.models import Session as DBSession
from states import MainMenu
from keyboards.builder import main_menu
from texts.common import BACK_TO_MENU_TEXT

class SessionManager:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.active_checks = {}

    async def start_session(
        self,
        db_session: AsyncSession,
        user_id: int,
        session_length_minutes: int
    ) -> int:
        """Создает новую сессию в БД и возвращает её ID"""
        expires_at = datetime.utcnow() + timedelta(minutes=session_length_minutes)
        
        db_sess = DBSession(
            user_id=user_id,
            started_at=datetime.utcnow(),
            expires_at=expires_at,
            is_active=True
        )
        
        db_session.add(db_sess)
        await db_session.commit()
        await db_session.refresh(db_sess)
        
        # Запускаем фоновую задачу для проверки времени
        self.active_checks[user_id] = asyncio.create_task(
            self._check_session_timeout(user_id, expires_at)
        )
        
        return db_sess.id

    async def _check_session_timeout(self, user_id: int, expires_at: datetime):
        """Фоновая задача для проверки времени сессии"""
        try:
            time_left = (expires_at - datetime.utcnow()).total_seconds()
            if time_left > 0:
                await asyncio.sleep(time_left)
            
            await self.notify_session_end(user_id)
        except Exception as e:
            print(f"Error in session timeout check: {e}")

    async def notify_session_end(self, user_id: int):
        """Уведомляет пользователя об окончании сессии"""
        try:
            await self.bot.send_message(
                user_id,
                "⌛️ Время сессии истекло. Сессия сохранена."
            )
            await self.bot.send_message(
                user_id,
                BACK_TO_MENU_TEXT,
                reply_markup=main_menu()
            )
        except Exception as e:
            print(f"Error sending session end notification: {e}")

    async def is_session_active(
        self,
        user_id: int,
        db_session: AsyncSession
    ) -> bool:
        """Проверяет, активна ли сессия пользователя"""
        stmt = select(DBSession).where(
            DBSession.user_id == user_id,
            DBSession.is_active == True
        ).order_by(DBSession.started_at.desc()).limit(1)
        
        result = await db_session.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            return False
        
        if datetime.utcnow() > session.expires_at:
            session.is_active = False
            await db_session.commit()
            return False
        
        return True

    async def cleanup(self):
        """Очистка при завершении работы"""
        for task in self.active_checks.values():
            task.cancel()
        self.active_checks.clear()