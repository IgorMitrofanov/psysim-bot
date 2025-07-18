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
from config import logger 
import json

class SessionManager:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.active_checks = {}
        self.message_history = {} 

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
        
        # Инициализируем историю сообщений для пользователя
        self.message_history[user_id] = {
            'user_messages': [],
            'bot_messages': [],
            'session_id': db_sess.id
        }
        
        # Запускаем фоновую задачу для проверки времени
        self.active_checks[user_id] = asyncio.create_task(
            self._check_session_timeout(user_id, db_sess.id, expires_at, db_session)
        )
        
        return db_sess.id
    
    async def _send_warning(self, user_id: int, session_id: int):
        """Отправляет предупреждение за 5 минут до конца"""
        try:
            if user_id in self.message_history:
                persona = self.message_history[user_id].get('persona')
                if persona:
                    warning_msg = persona.get_warning_message()
                    await self.bot.send_message(user_id, warning_msg)
        except Exception as e:
            logger.error(f"Error sending warning message: {e}")

    async def _check_session_timeout(self, user_id: int, session_id: int, expires_at: datetime, db_session: AsyncSession):
        """Фоновая задача для проверки времени сессии"""
        try:
            # Отправляем предупреждение за 5 минут до конца
            warning_time = expires_at - timedelta(minutes=5)
            time_to_warning = (warning_time - datetime.utcnow()).total_seconds()
            
            if time_to_warning > 0:
                await asyncio.sleep(time_to_warning)
                await self._send_warning(user_id, session_id)

            # Ожидаем оставшееся время
            time_left = (expires_at - datetime.utcnow()).total_seconds()
            if time_left > 0:
                await asyncio.sleep(time_left)
            
            # Завершаем сессию с отправкой последнего сообщения
            await self._end_session_with_farewell(user_id, session_id, db_session)
            
        except Exception as e:
            logger.error(f"Error in session timeout check: {e}")
            
    async def _end_session_with_farewell(self, user_id: int, session_id: int, db_session: AsyncSession):
        """Завершает сессию с отправкой прощального сообщения"""
        try:
            # Получаем персонажа для прощального сообщения
            persona = None
            if user_id in self.message_history:
                persona = self.message_history[user_id].get('persona')
            
            # Отправляем последнее сообщение от персонажа
            if persona:
                last_response = await persona.send("Время сессии вышло, пора попрощаться.")
                await self.bot.send_message(user_id, last_response)
            
            # Завершаем сессию
            await self.end_session(user_id, session_id, db_session)
            
            # Отправляем уведомление о завершении
            await self.notify_session_end(user_id)
            
        except Exception as e:
            logger.error(f"Error in session farewell: {e}")

    async def end_session(self, user_id: int, session_id: int, db_session: AsyncSession):
        """Завершает сессию и сохраняет данные"""
        try:
            # Получаем сессию из БД
            stmt = select(DBSession).where(
                DBSession.id == session_id,
                DBSession.user_id == user_id
            )
            result = await db_session.execute(stmt)
            session = result.scalar_one_or_none()
            
            if session:
                # Сохраняем историю сообщений
                history = self.message_history.get(user_id, {})
                
                session.ended_at = datetime.utcnow()
                session.is_active = False
                session.user_messages = json.dumps(history.get('user_messages', []), ensure_ascii=False)
                session.bot_messages = json.dumps(history.get('bot_messages', []), ensure_ascii=False)
                
                await db_session.commit()
                
                # Удаляем историю сообщений из памяти
                if user_id in self.message_history:
                    del self.message_history[user_id]
                
                # Отменяем таймер, если он есть
                if user_id in self.active_checks:
                    self.active_checks[user_id].cancel()
                    del self.active_checks[user_id]
                
                return True
            return False
        except Exception as e:
            logger.error(f"Error ending session: {e}")
            return False

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
            logger.error(f"Error sending session end notification: {e}")

    async def add_message_to_history(self, user_id: int, message: str, is_user: bool):
        """Добавляет сообщение в историю сессии"""
        if user_id not in self.message_history:
            return
            
        if is_user:
            self.message_history[user_id]['user_messages'].append(message)
        else:
            self.message_history[user_id]['bot_messages'].append(message)

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
            await self.end_session(user_id, session.id, db_session)
            return False
        
        return True

    async def cleanup(self):
        """Очистка при завершении работы"""
        for task in self.active_checks.values():
            task.cancel()
        self.active_checks.clear()