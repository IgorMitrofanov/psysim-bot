from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import asyncio
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database.models import Session
from database.models import Tariff, TariffType, Session, Order
from database.crud import get_user_by_id, get_telegram_id_by_user_id
from keyboards.builder import main_menu
from texts.common import BACK_TO_MENU_TEXT
from config import logger 
import json
from config import config
from asyncio import Lock
from core.persones.persona_loader import PersonaLoader
from core.reports.supervision_report_builder import SupervisionReportBuilder
from core.reports.supervision_report_builder_low_cost import SimpleSupervisionReportBuilder
from services.achievements import AchievementSystem


# --- Менеджер сессий ---
# Осуществляет управление сессиями: начало, окончание, нотификация юзера, хранение данных сессии и их запись в БД
class SessionManager:
    def __init__(self, bot: Bot, engine, achievement_system: AchievementSystem):
        self.bot = bot            # Инстанс бот
        self.active_checks = {}   # Список активных сессий для таймера
        self.message_history = {} # История сообщений - юзера и персоны
        self.session_ended = {}   # Флаг окончания сессии для каждого пользователя
        self.lock = Lock()
        self.persona_loader = PersonaLoader(engine)
        self.achievement_system = achievement_system

    async def start_session(
        self,
        db_session: AsyncSession,
        user_id: int,
        is_free: bool,
        persona_name:str,
        resistance:str,
        emotion:str,
        is_rnd: bool=False, # Случайная ли сессия (настройки сопротивления, эмоции и персонаж). Флаг заложен для ачивок и статистики
    ) -> int:
        """Создает новую сессию в БД и возвращает её ID"""
        # Получаем пользователя
        user = await get_user_by_id(db_session, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        # Длина сессии из конфига приложения
        session_length = config.SESSION_LENGTH_MINUTES
        expires_at = datetime.utcnow() + timedelta(minutes=int(session_length))
        # Запись в БД
        db_sess = Session(
            user_id=user_id,
            started_at=datetime.utcnow(),
            expires_at=expires_at,
            is_active=True,
            is_free=is_free,
            is_rnd=is_rnd,
            emotional=emotion,
            resistance_level=resistance,
            persona_name=persona_name
        )
        user.last_activity = datetime.utcnow()
        db_session.add(db_sess)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(db_sess)
        
        # Инициализируем историю сообщений для пользователя
        self.message_history[user_id] = {
            'user_messages': [],
            'bot_messages': [],
            'session_id': db_sess.id,
            'persona_id': None,
            'tokens_spent': 0
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
    
    async def get_persona(self, name: str) -> Optional[Dict]:
        return await self.persona_loader.get_persona(name)
    
    async def get_all_personas(self) -> Dict[str, Dict]:
        return await self.persona_loader.load_all_personas()
    
    async def _send_warning(self, user_id: int, session_id: int, db_session: AsyncSession):
        """Отправляет предупреждение за N минут до конца"""
        try:
            if user_id in self.message_history and not self.session_ended.get(user_id, False):
                session_data = self.message_history[user_id]
                stmt = select(Session).where(Session.id == session_data['session_id'])
                result = await db_session.execute(stmt)
                session = result.scalar_one_or_none()
                
                if session:
                    time_left = session.expires_at - datetime.utcnow()
                    minutes_left = int(time_left.total_seconds() // 60)
                    
                    warning_msg = (
                        f"⏳ Осталось {minutes_left + 1} минут до окончания сессии.\n" # с учетом округления в меньшую сторону + 1
                    )
                    telegram_id = await get_telegram_id_by_user_id(db_session, user_id)
                    await self.bot.send_message(telegram_id, warning_msg)
                    logger.info(f"Warning sent to user {user_id} ({minutes_left + 1} minutes left)")
        except Exception as e:
            logger.error(f"Error sending warning message: {e}")

    async def _check_session_timeout(self, user_id: int, session_id: int, expires_at: datetime, db_session: AsyncSession):
        """Фоновая задача для проверки времени сессии"""
        try:
            # Логгируем время до конца сессии
            time_left = (expires_at - datetime.utcnow()).total_seconds()
            minutes, seconds = divmod(time_left, 60)
            logger.info(f"Session check started for user {user_id}. Time left: {int(minutes)}m {int(seconds)}s")
            
            # Отправляем предупреждение за N минут до конца - берется из конфига приложения
            warning_time = expires_at - timedelta(minutes=int(config.WARNING_BEFORE_END_MINUTES))
            time_to_warning = (warning_time - datetime.utcnow()).total_seconds()
            
            if time_to_warning > 0:
                logger.info(f"Will send warning to user {user_id} in {time_to_warning} seconds")
                await asyncio.sleep(time_to_warning)

                # Проверка до отправки предупреждения, может сессия уже закончилась?
                if self.session_ended.get(user_id):
                    logger.info(f"Skipping warning for user {user_id} because session was aborted.")
                    return
                # Предупреждаем
                await self._send_warning(user_id, session_id, db_session)
                    
            # Ожидаем оставшееся время
            time_left = (expires_at - datetime.utcnow()).total_seconds()
            if time_left > 0:
                logger.info(f"Waiting {time_left} seconds until session end for user {user_id}")
                await asyncio.sleep(time_left)
            # Завершаем сессиию
            await self.end_session(user_id, session_id, db_session, )
            
        except asyncio.CancelledError:
            logger.info(f"Session check cancelled for user {user_id}")
        except Exception as e:
            logger.error(f"Error in session timeout check: {e}")
            

    async def end_session(self, user_id: int, session_id: int, db_session: AsyncSession):
        """Завершает сессию и сохраняет данные"""
        try:
            async with self.lock:
                # Проверяем, не завершена ли уже сессия
                if self.session_ended.get(user_id, False):
                    return False

                # Получаем сессию с явным указанием на необходимости обновления
                stmt = select(Session).where(
                    Session.id == session_id,
                    Session.user_id == user_id
                ).with_for_update()  # Блокируем запись для обновления
                
                try:
                    result = await db_session.execute(stmt)
                    session = result.scalar_one_or_none()
                    
                    if not session:
                        logger.warning(f"Session {session_id} not found for user {user_id}")
                        return False
                    
                    # Получаем информацию о тарифе пользователя
                    user = await get_user_by_id(db_session, user_id)
                    if not user:
                        logger.warning(f"User {user_id} not found")
                        return False
                    
                    # Подготовка данных для отчета
                    history = self.message_history.get(user_id, {})
                    user_messages = history.get('user_messages', [])
                    bot_messages = history.get('bot_messages', [])
                    
                    # Собираем историю сессии для отчета
                    session_history = []
                    for user_msg, bot_msg in zip(user_messages, bot_messages):
                        session_history.append({"role": "Терапевт", "content": user_msg})
                        session_history.append({"role": "Пациент", "content": bot_msg})
                    
                    # Генерируем отчет, если есть имя персоны
                    report_text = None
                    report_tokens = 0
                    telegram_id = await get_telegram_id_by_user_id(db_session, user_id)
                    
                    # Создаем задачу для анимации точек
                    dots_task = None
                    status_message = None
                    
                    async def update_loading_message():
                        nonlocal status_message
                        dots = ["", ".", "..", "..."]
                        i = 0
                        while True:
                            try:
                                if not status_message:
                                    status_message = await self.bot.send_message(
                                        telegram_id,
                                        f"<i>Генерация супервизорского отчета по сессии{dots[i]}</i>",
                                        parse_mode="HTML"
                                    )
                                else:
                                    await self.bot.edit_message_text(
                                        f"<i>Генерация супервизорского отчета по сессии{dots[i]}</i>",
                                        chat_id=telegram_id,
                                        message_id=status_message.message_id,
                                        parse_mode="HTML"
                                    )
                                
                                i = (i + 1) % len(dots)
                                await asyncio.sleep(0.5)  # Интервал обновления
                            except Exception as e:
                                logger.warning(f"Error updating loading message: {e}")
                                break

                    if session.persona_name:
                        try:
                            # Запускаем анимацию перед генерацией отчета
                            dots_task = asyncio.create_task(update_loading_message())
                            
                            if user.active_tariff in [TariffType.PRO, TariffType.UNLIMITED]:
                                report_builder = SupervisionReportBuilder(
                                    persona_loader=self.persona_loader,
                                    session_history=session_history
                                )
                                report_text, report_tokens = await report_builder.generate_report(session.persona_name)
                                logger.info(f"Generated full supervision report for session {session_id}, tokens used: {report_tokens}")
                            else:
                                report_builder = SimpleSupervisionReportBuilder(
                                    persona_loader=self.persona_loader,
                                    session_history=session_history
                                )
                                report_text, report_tokens = await report_builder.generate_report(session.persona_name)
                                logger.info(f"Generated low-cost supervision report for session {session_id}, tokens used: {report_tokens}")
                        except Exception as e:
                            logger.error(f"Error generating supervision report: {e}")
                            raise
                        finally:
                            # Останавливаем анимацию в любом случае
                            if dots_task:
                                dots_task.cancel()
                                try:
                                    await dots_task
                                except asyncio.CancelledError:
                                    pass
                            
                            # Удаляем сообщение о загрузке, если оно было отправлено
                            if status_message:
                                try:
                                    await self.bot.delete_message(
                                        chat_id=telegram_id,
                                        message_id=status_message.message_id
                                    )
                                except Exception as e:
                                    logger.warning(f"Error deleting loading message: {e}")
                    
                    # Обновляем данные сессии
                    history = self.message_history.get(user_id, {})
                    session.ended_at = datetime.utcnow()
                    session.is_active = False
                    session.report_text = report_text
                    
                    # Отправляем отчет пользователю, если он сгенерирован
                    if report_text:
                        try:
                            # Разделяем текст на части по 4000 символов (с запасом)
                            chunk_size = 4000
                            report_chunks = [report_text[i:i+chunk_size] for i in range(0, len(report_text), chunk_size)]
                            
                            for chunk in report_chunks:
                                await self.bot.send_message(
                                    telegram_id,
                                    chunk,
                                    parse_mode="HTML"
                                )
                                # Небольшая пауза между сообщениями
                                await asyncio.sleep(0.5)
                                
                            logger.info(f"Report sent to user {user_id} in {len(report_chunks)} parts")
                        except Exception as e:
                            logger.error(f"Error sending report: {e}")
                    
                    try:
                        session.user_messages = json.dumps(history.get('user_messages', []), ensure_ascii=False)
                        session.bot_messages = json.dumps(history.get('bot_messages', []), ensure_ascii=False)
                    except Exception as e:
                        logger.error(f"Error serializing messages: {e}")
                        # Сохраняем хотя бы информацию об ошибке
                        session.user_messages = "[]"
                        session.bot_messages = "[]"
                    
                    session.tokens_spent = history.get('tokens_spent', 0) + report_tokens
                    
                    # Устанавливаем persona_id если есть имя персоны
                    if session.persona_name:
                        # Получаем персону из кэша или базы данных
                        persona_dict = await self.persona_loader.get_persona(session.persona_name)
                        if persona_dict and 'persona' in persona_dict:
                            session.persona_id = persona_dict['persona']['id']
                            logger.debug(f"Set persona_id={session.persona_id} for session {session_id}")
                        else:
                            logger.warning(f"Persona '{session.persona_name}' not found for session {session_id}")
                    
                    try:
                        await db_session.commit()
                    except Exception as e:
                        logger.error(f"Commit failed: {e}")
                        await db_session.rollback()
                        return False
                    
                    # Очищаем данные только после успешного коммита
                    if user_id in self.message_history:
                        del self.message_history[user_id]
                    
                    # Отменяем задачу проверки таймаута
                    if user_id in self.active_checks:
                        task = self.active_checks[user_id]
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                        del self.active_checks[user_id]
                    
                    await asyncio.sleep(1) # Небольшая пауза перед отправкой уведомления
                    
                    # Отправляем уведомление
                    try:
                        await self._check_session_achievements(user_id, db_session, session)
                        await self.notify_session_end(user_id, db_session)
                        logger.info(f"Session {session_id} successfully ended for user {user_id}")
                        return True
                    except Exception as e:
                        logger.error(f"Error notifying session end: {e}")
                        return False
                    
                except Exception as e:
                    logger.error(f"Error updating session in DB: {e}")
                    await db_session.rollback()
                    return False
                    
        except Exception as e:
            logger.error(f"Unexpected error in end_session: {e}")
            return False

    async def add_message_to_history(self, user_id: int, message: str, is_user: bool, tokens_used: int):
        """Добавляет сообщение и примерное количество токенов в историю сессии"""
        async with self.lock:
            if user_id not in self.message_history or self.session_ended.get(user_id, False):
                return

            if is_user:
                self.message_history[user_id]['user_messages'].append(message)
            else:
                self.message_history[user_id]['bot_messages'].append(message)

            self.message_history[user_id]['tokens_spent'] = (
                self.message_history[user_id].get('tokens_spent', 0) + tokens_used
            )

    async def is_session_active(
        self,
        user_id: int,
        db_session: AsyncSession
    ) -> bool:
        """Проверяет, активна ли сессия пользователя"""
        if self.session_ended.get(user_id, False):
            return False
            
        stmt = select(Session).where(
            Session.user_id == user_id,
            Session.is_active == True
        ).order_by(Session.started_at.desc()).limit(1)
        
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
        tasks = list(self.active_checks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.active_checks.clear()
        self.message_history.clear()
        self.session_ended.clear()
        
    async def use_session_quota_or_bonus(
        self,
        db_session: AsyncSession, 
        user_id: int
    ) -> Tuple[bool, bool]:
        """
        Проверяет, можно ли использовать квоту или бонус.
        Возвращает:
        - (True, False) — можно использовать квоту
        - (True, True)  — можно использовать бонус
        - (False, False) — нет доступных ресурсов
        
        Особенности:
        - Не учитывает бесплатные подписки (TRIAL) при проверке квоты
        - Обновляет квоту при смене тарифа
        """
        user = await get_user_by_id(db_session, user_id)
        if not user:
            return False, False

        # Если тариф TRIAL, сразу используем бонус (если есть)
        if user.active_tariff == TariffType.TRIAL:
            if user.bonus_balance > 0:
                user.bonus_balance -= 1
                await db_session.commit()
                return True, True
            return False, False

        tariff = await db_session.execute(
            select(Tariff).where(Tariff.name == user.active_tariff)
        )
        tariff = tariff.scalar_one_or_none()
        
        if not tariff:
            return False, False

        # Получаем дату активации текущего тарифа
        last_order = await db_session.execute(
            select(Order)
            .where(Order.user_id == user.id)
            .where(Order.tariff_id == tariff.id)
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        last_order = last_order.scalar_one_or_none()
        
        quota_start_date = last_order.created_at
        quota_period_days = getattr(tariff, "quota_period_days", 30)

        # Получаем количество сессий в текущем периоде квоты (исключая бесплатные)
        sessions_in_period = await db_session.execute(
            select(func.count(Session.id))
            .where(Session.user_id == user.id)
            .where(Session.started_at >= quota_start_date)
            .where(Session.is_free == False)  # Исключаем бесплатные сессии
        )
        sessions_in_period = sessions_in_period.scalar() or 0

        # Проверяем квоту
        if sessions_in_period < tariff.session_quota:
            return True, False

        # Проверяем бонусы
        if user.bonus_balance > 0:
            user.bonus_balance -= 1
            await db_session.commit()
            return True, True

        return False, False
        
    async def notify_session_end(self, user_id: int, db_session: AsyncSession):
        """Уведомляет пользователя об окончании сессии"""
        telegram_id = await get_telegram_id_by_user_id(db_session, user_id)
        try:
            await self.bot.send_message(
                telegram_id,
                "⌛️ Время сессии истекло. Сессия сохранена."
            )
            await self.bot.send_message(
                telegram_id,
                BACK_TO_MENU_TEXT,
                reply_markup=main_menu()
            )
            logger.info(f"Session end notification sent to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending session end notification: {e}")
            
    async def _check_session_achievements(self, user_id: int, db_session: AsyncSession, session: Session):
        """Проверяет достижения после сессии"""
        try:
            if self.achievement_system:
                session_data = {
                    'started_at': session.started_at,
                    'ended_at': session.ended_at,
                    'resistance_level': session.resistance_level,
                    'emotional': session.emotional,
                    'persona_id': session.persona_id,
                    'is_rnd': session.is_rnd,
                    'tokens_spent': session.tokens_spent,
                    'persona_name': session.persona_name
                }
                
                await self.achievement_system.check_session_achievements(user_id, session_data)
                logger.info(f"Achievements checked for user {user_id} after session {session.id}")
        except Exception as e:
            logger.error(f"Error checking achievements: {e}", exc_info=True)