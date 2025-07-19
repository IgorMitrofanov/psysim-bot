from datetime import datetime, timedelta
from typing import Optional
import asyncio
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.models import Session as DBSession
from database.crud import get_sessions_today_count
from states import MainMenu
from keyboards.builder import main_menu
from texts.common import BACK_TO_MENU_TEXT
from config import logger 
import json
from config import config

class SessionManager:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.active_checks = {}
        self.message_history = {} 
        self.session_ended = {}  # Флаг окончания сессии для каждого пользователя

    async def start_session(
        self,
        db_session: AsyncSession,
        user_id: int,
        is_free: bool,
        persona_name:str,
        resistance:str,
        emotion:str
    ) -> int:
        """Создает новую сессию в БД и возвращает её ID"""
        session_length = config.SESSION_LENGTH_MINUTES
        expires_at = datetime.utcnow() + timedelta(minutes=int(session_length))
        
        db_sess = DBSession(
            user_id=user_id,
            started_at=datetime.utcnow(),
            expires_at=expires_at,
            is_active=True,
            is_free=is_free,
            emotional=emotion,
            resistance_level=resistance,
            persona_name=persona_name
        )
        
        db_session.add(db_sess)
        await db_session.commit()
        await db_session.refresh(db_sess)
        
        # Инициализируем историю сообщений для пользователя
        self.message_history[user_id] = {
            'user_messages': [],
            'bot_messages': [],
            'session_id': db_sess.id,
            'persona': None
        }
        
        # Сбрасываем флаг окончания сессии
        self.session_ended[user_id] = False
        
        # Запускаем фоновую задачу для проверки времени
        self.active_checks[user_id] = asyncio.create_task(
            self._check_session_timeout(user_id, db_sess.id, expires_at, db_session)
        )
        
        logger.info(f"Session started for user {user_id}. Duration: {config.SESSION_LENGTH_MINUTES} minutes. "
                   f"Expires at: {expires_at}")
        
        return db_sess.id
    
    async def _send_warning(self, user_id: int, session_id: int, db_session: AsyncSession):
        """Отправляет предупреждение за 5 минут до конца"""
        try:
            if user_id in self.message_history and not self.session_ended.get(user_id, False):
                session_data = self.message_history[user_id]
                stmt = select(DBSession).where(DBSession.id == session_data['session_id'])
                result = await db_session.execute(stmt)
                session = result.scalar_one_or_none()
                
                if session:
                    time_left = session.expires_at - datetime.utcnow()
                    minutes_left = int(time_left.total_seconds() // 60)
                    
                    warning_msg = (
                        f"⏳ Осталось {minutes_left + 1} минут до окончания сессии.\n" # с учетом округления в меньшую сторону + 1
                    )
                    
                    await self.bot.send_message(user_id, warning_msg)
                    logger.info(f"Warning sent to user {user_id} ({minutes_left} minutes left)")
        except Exception as e:
            logger.error(f"Error sending warning message: {e}")

    async def _check_session_timeout(self, user_id: int, session_id: int, expires_at: datetime, db_session: AsyncSession):
        """Фоновая задача для проверки времени сессии"""
        try:
            # Логгируем время до конца сессии
            time_left = (expires_at - datetime.utcnow()).total_seconds()
            minutes, seconds = divmod(time_left, 60)
            logger.info(f"Session check started for user {user_id}. Time left: {int(minutes)}m {int(seconds)}s")
            
            # Отправляем предупреждение за 5 минут до конца
            warning_time = expires_at - timedelta(minutes=int(config.WARNING_BEFORE_END_MINUTES))
            time_to_warning = (warning_time - datetime.utcnow()).total_seconds()
            
            if time_to_warning > 0:
                logger.info(f"Will send warning to user {user_id} in {time_to_warning} seconds")
                await asyncio.sleep(time_to_warning)

                # ПРОВЕРКА ДО ОТПРАВКИ ПРЕДУПРЕЖДЕНИЯ
                if self.session_ended.get(user_id):
                    logger.info(f"Skipping warning for user {user_id} because session was aborted.")
                    return

                await self._send_warning(user_id, session_id, db_session)
                    
            # Ожидаем оставшееся время
            time_left = (expires_at - datetime.utcnow()).total_seconds()
            if time_left > 0:
                logger.info(f"Waiting {time_left} seconds until session end for user {user_id}")
                await asyncio.sleep(time_left)
                
            await self.end_session(user_id, session_id, db_session)
            self.session_ended[user_id] = True
            await self.notify_session_end(user_id)
            
        except asyncio.CancelledError:
            logger.info(f"Session check cancelled for user {user_id}")
        except Exception as e:
            logger.error(f"Error in session timeout check: {e}")
            
    async def abort_session(self, user_id: int, db_session: AsyncSession, session_id: Optional[int] = None):
        """
        Принудительно завершает сессию и удаляет её из БД.
        Также очищает состояние в памяти и отменяет таймер.
        """
        try:
            self.session_ended[user_id] = True

            # Получаем session_id из памяти, если не передан
            if not session_id and user_id in self.message_history:
                session_id = self.message_history[user_id].get("session_id")

            # Удаляем сессию из БД, если нашли
            if session_id:
                stmt = select(DBSession).where(DBSession.id == session_id)
                result = await db_session.execute(stmt)
                session = result.scalar_one_or_none()
                if session:
                    await db_session.delete(session)
                    await db_session.commit()
                    logger.info(f"Session {session_id} deleted from DB for user {user_id}")
                else:
                    logger.warning(f"No session found in DB to delete for user {user_id} (session_id={session_id})")

            # Удаляем историю сообщений из памяти
            if user_id in self.message_history:
                del self.message_history[user_id]

            # Отменяем таймер, если он есть
            if user_id in self.active_checks:
                self.active_checks[user_id].cancel()
                del self.active_checks[user_id]

            logger.info(f"Session aborted for user {user_id} (removed from memory and DB)")
            return True
        except Exception as e:
            logger.error(f"Error aborting session for user {user_id}: {e}")
            return False


    async def end_session(self, user_id: int, session_id: int, db_session: AsyncSession, persona: Optional[object] = None):
        """Завершает сессию и сохраняет данные"""
        try:
            # Устанавливаем флаг окончания сессии
            self.session_ended[user_id] = True
            
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
                session.tokens_spent = history.get('tokens_spent', 0)

                if persona:
                    session.resistance_level = persona.resistance_level
                    session.emotional = persona.emotional_state
                    session.format = persona.format
                
                await db_session.commit()
                
                # Удаляем историю сообщений из памяти
                if user_id in self.message_history:
                    del self.message_history[user_id]
                
                # Отменяем таймер, если он есть
                if user_id in self.active_checks:
                    self.active_checks[user_id].cancel()
                    del self.active_checks[user_id]
                
                logger.info(f"Session {session_id} ended for user {user_id}")
                return True
            
            logger.warning(f"No active session found for user {user_id} to end")
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
            logger.info(f"Session end notification sent to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending session end notification: {e}")

    async def add_message_to_history(self, user_id: int, message: str, is_user: bool):
        """Добавляет сообщение и примерное количество токенов в историю сессии"""
        if user_id not in self.message_history or self.session_ended.get(user_id, False):
            return

        if is_user:
            self.message_history[user_id]['user_messages'].append(message)
        else:
            self.message_history[user_id]['bot_messages'].append(message)

        # Примерная оценка токенов: 1 токен ≈ 4 символа
        estimated_tokens = max(1, len(message) // 4)
        self.message_history[user_id]['tokens_spent'] = (
            self.message_history[user_id].get('tokens_spent', 0) + estimated_tokens
        )

    async def is_session_active(
        self,
        user_id: int,
        db_session: AsyncSession
    ) -> bool:
        """Проверяет, активна ли сессия пользователя"""
        if self.session_ended.get(user_id, False):
            return False
            
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
        
        # Логгируем оставшееся время
        time_left = session.expires_at - datetime.utcnow()
        minutes, seconds = divmod(time_left.total_seconds(), 60)
        logger.info(f"Session active for user {user_id}. Time left: {int(minutes)}m {int(seconds)}s")
        
        return True

    async def cleanup(self):
        """Очистка при завершении работы"""
        for user_id, task in self.active_checks.items():
            task.cancel()
            logger.info(f"Cancelled session check for user {user_id}")
        self.active_checks.clear()
        self.message_history.clear()
        self.session_ended.clear()
        
    async def use_session_quota_or_bonus(self, db_session: AsyncSession, user) -> tuple[bool, bool]:
        """
        Пытается использовать квоту или бонус:
        - Возвращает (True, False) если сессия списана из квоты
        - Возвращает (True, True) если сессия списана из бонусов
        - Возвращает (False, False) если ресурсов нет
        """
        quota = config.TARIFF_QUOTAS.get(user.active_tariff, 0)
        sessions_today = await get_sessions_today_count(db_session, user.id)

        if sessions_today < quota:
            # Использована квота
            return True, False
        elif user.bonus_balance > 0:
            # Использован бонус
            user.bonus_balance -= 1
            await db_session.commit()
            return True, True
        else:
            # Ресурсов нет
            return False, False