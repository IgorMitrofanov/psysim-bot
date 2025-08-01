
from typing import Dict, List, Any
import datetime
from collections import defaultdict
from database.models import Achievement, User, Session, AchievementType, AchievementTier, AchievementProgress, Referral, Feedback
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, extract
import asyncio
import sqlalchemy.exc

from .achievement_config import ach_config, ach_names

from config import logger

class AchievementSystem:
    def __init__(self, bot, sessionmaker):
        self.bot = bot
        self.sessionmaker = sessionmaker
        self.max_retries = 3
        self.retry_delay = 0.1
        
        # Конфигурация достижений
        self.achievement_config = ach_config
        
        logger.info("AchievementSystem initialized with configuration for %d achievement types", len(self.achievement_config))
    
    async def check_achievements(self, user_id: int, achievement_type: AchievementType, progress_increment: int = 1) -> List[Achievement]:
        """Проверяет и выдает достижения с повторными попытками при блокировке"""
        logger.debug(
            "Checking achievements for user %d, type %s, increment %d",
            user_id, achievement_type.name, progress_increment
        )
        
        for attempt in range(self.max_retries):
            async with self.sessionmaker() as session:
                try:
                    # Получаем текущие достижения пользователя
                    result = await session.execute(
                        select(Achievement)
                        .filter(
                            Achievement.user_id == user_id,
                            Achievement.badge_code == achievement_type
                        )
                    )
                    user_achievements = result.scalars().all()
                    
                    logger.debug(
                        "User %d already has %d achievements of type %s",
                        user_id, len(user_achievements), achievement_type.name
                    )
                    
                    # Получаем общий прогресс
                    total_progress = await self._get_total_progress(
                        session, user_id, achievement_type, progress_increment
                    )
                    
                    logger.debug(
                        "Total progress for user %d, achievement %s: %d",
                        user_id, achievement_type.name, total_progress
                    )
                    
                    # Получаем конфигурацию для этого типа достижения
                    config = self.achievement_config.get(achievement_type, {})
                    new_achievements = []
                    
                    # Проверяем каждый уровень в порядке возрастания
                    for tier in [AchievementTier.BRONZE, AchievementTier.SILVER, 
                                AchievementTier.GOLD, AchievementTier.PLATINUM]:
                        if tier not in config:
                            continue
                        
                        # Если достижение уже получено, пропускаем
                        if any(ach.tier == tier for ach in user_achievements):
                            logger.debug(
                                "User %d already has %s tier for %s, skipping",
                                user_id, tier.name, achievement_type.name
                            )
                            continue
                        
                        # Проверяем, достигнут ли требуемый прогресс
                        if total_progress >= config[tier]['required']:
                            new_ach = Achievement(
                                user_id=user_id,
                                badge_code=achievement_type,
                                tier=tier,
                                progress=100,
                                points=config[tier]['points'],
                                awarded_at=datetime.datetime.utcnow()
                            )
                            session.add(new_ach)
                            new_achievements.append(new_ach)
                            
                            logger.info(
                                "Awarded new achievement to user %d: %s (%s), progress %d/%d",
                                user_id, achievement_type.name, tier.name,
                                total_progress, config[tier]['required']
                            )
                            
                            # Отправляем уведомление (вне транзакции)
                            asyncio.create_task(self._notify_user(user_id, achievement_type, tier))
                    
                    if new_achievements:
                        await session.commit()
                        logger.info(
                            "Committed %d new achievements for user %d, type %s",
                            len(new_achievements), user_id, achievement_type.name
                        )
                    else:
                        logger.debug("No new achievements to award")
                    
                    return new_achievements
                    
                except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.DBAPIError) as e:
                    await session.rollback()
                    if "database is locked" in str(e) and attempt < self.max_retries - 1:
                        wait_time = self.retry_delay * (attempt + 1)
                        logger.warning(
                            "Database locked (attempt %d/%d), retrying in %.2f sec...",
                            attempt + 1, self.max_retries, wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    logger.error(
                        "Error checking achievements for user %d, type %s (attempt %d): %s",
                        user_id, achievement_type.name, attempt + 1, str(e),
                        exc_info=True
                    )
                    return []
                except Exception as e:
                    await session.rollback()
                    logger.error(
                        "Unexpected error checking achievements for user %d, type %s: %s",
                        user_id, achievement_type.name, str(e),
                        exc_info=True
                    )
                    return []
        
        logger.warning(
            "Max retries (%d) exceeded for user %d, type %s",
            self.max_retries, user_id, achievement_type.name
        )
        return []
    
    async def _notify_user(self, user_id: int, achievement_type: AchievementType, tier: AchievementTier):
        """Отправляет уведомление пользователю о новом достижении"""
        try:
            logger.debug(
                "Preparing to notify user %d about new achievement %s (%s)",
                user_id, achievement_type.name, tier.name
            )
            
            async with self.sessionmaker() as session:
                result = await session.execute(
                    select(User).filter(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    logger.warning("User %d not found for achievement notification", user_id)
                    return
                
                message = (
                    f"🎉 Поздравляем! Вы получили достижение!\n\n"
                    f"🏆 <b>{self._get_achievement_name(achievement_type)} ({self._get_tier_name(tier)})</b>\n\n"
                    f"Продолжайте в том же духе!"
                )
                
                logger.info(
                    "Sending achievement notification to user %d (%s): %s (%s)",
                    user_id, user.telegram_id, achievement_type.name, tier.name
                )
                
                await self.bot.send_message(chat_id=user.telegram_id, text=message, parse_mode='HTML')
                
        except Exception as e:
            logger.error(
                "Error notifying user %d about achievement %s (%s): %s",
                user_id, achievement_type.name, tier.name, str(e),
                exc_info=True
            )

    def _get_achievement_name(self, achievement_type: AchievementType) -> str:
        """Возвращает читаемое название достижения"""
        
        return ach_names.get(achievement_type, "Достижение")
    
    def _get_tier_name(self, tier: AchievementTier) -> str:
        """Возвращает читаемое название уровня достижения"""
        names = {
            AchievementTier.BRONZE: "Бронза",
            AchievementTier.SILVER: "Серебро",
            AchievementTier.GOLD: "Золото",
            AchievementTier.PLATINUM: "Платина"
        }
        return names.get(tier, "")
    
    async def _get_total_progress(self, session: AsyncSession, user_id: int, 
                                achievement_type: AchievementType, increment: int) -> int:
        """Вычисляет общий прогресс для достижения"""
        try:
            logger.debug(
                "Calculating total progress for user %d, achievement %s",
                user_id, achievement_type.name
            )
            
            if achievement_type == AchievementType.FEEDBACK_CONTRIBUTOR:
                count = (await session.execute(
                    select(func.count()).select_from(Feedback)
                    .filter(Feedback.user_id == user_id)
                )).scalar() or 0
                logger.debug("Feedback count for user %d: %d", user_id, count)
                return count
            
            elif achievement_type == AchievementType.SESSION_COUNT:
                count = (await session.execute(
                    select(func.count()).select_from(Session)
                    .filter(Session.user_id == user_id)
                )).scalar() or 0
                logger.debug("Session count for user %d: %d", user_id, count)
                return count
            
            elif achievement_type == AchievementType.HIGH_RESISTANCE:
                count = (await session.execute(
                    select(func.count()).select_from(Session)
                    .filter(
                        Session.user_id == user_id,
                        Session.resistance_level == 'высокий'
                    )
                )).scalar() or 0
                logger.debug("High resistance sessions for user %d: %d", user_id, count)
                return count
            
            elif achievement_type == AchievementType.REFERRAL_MASTER:
                count = (await session.execute(
                    select(func.count()).select_from(Referral)
                    .filter(Referral.inviter_id == user_id)
                )).scalar() or 0
                logger.debug("Referrals count for user %d: %d", user_id, count)
                return count
            
            elif achievement_type == AchievementType.FIRST_SESSION:
                count = (await session.execute(
                    select(func.count()).select_from(Session)
                    .filter(Session.user_id == user_id)
                )).scalar() or 0
                has_session = 1 if count > 0 else 0
                logger.debug("First session check for user %d: %d", user_id, has_session)
                return has_session
            
            elif achievement_type == AchievementType.MONTHLY_CHALLENGE:
                now = datetime.datetime.utcnow()
                count = (await session.execute(
                    select(func.count()).select_from(Session)
                    .filter(
                        Session.user_id == user_id,
                        extract('month', Session.started_at) == now.month,
                        extract('year', Session.started_at) == now.year
                    )
                )).scalar() or 0
                logger.debug(
                    "Monthly sessions for user %d (%d-%d): %d",
                    user_id, now.month, now.year, count
                )
                return count
            
            elif achievement_type == AchievementType.PERSONA_COLLECTOR:
                count = (await session.execute(
                    select(func.count(func.distinct(Session.persona_id)))
                    .filter(
                        Session.user_id == user_id,
                        Session.persona_id.isnot(None)
                    )
                )).scalar() or 0
                logger.debug("Unique personas for user %d: %d", user_id, count)
                return count
            
            # Для остальных достижений используем AchievementProgress
            progress_record = await self._get_or_create_progress_record(
                session, user_id, achievement_type
            )
            
            # Инкрементируем прогресс для определенных типов достижений
            if achievement_type in [
                AchievementType.NIGHT_OWL,
                AchievementType.WEEKEND_WARRIOR,
                AchievementType.TIME_TRAVELER,
                AchievementType.THERAPY_MARATHON
            ]:
                old_progress = progress_record.progress
                progress_record.progress += increment
                await session.commit()
                logger.debug(
                    "Incremented progress for user %d, achievement %s: %d -> %d",
                    user_id, achievement_type.name, old_progress, progress_record.progress
                )
            elif achievement_type == AchievementType.EMOTIONAL_EXPLORER:
                # Для этого типа нужно считать уникальные эмоции
                unique_emotions = await self._count_unique_emotions(session, user_id)
                progress_record.progress = unique_emotions
                await session.commit()
                logger.debug(
                    "Updated EMOTIONAL_EXPLORER progress for user %d: %d unique emotions",
                    user_id, unique_emotions
                )
                
            return progress_record.progress
            
        except Exception as e:
            logger.error(
                "Error getting total progress for user %d, achievement %s: %s",
                user_id, achievement_type.name, str(e),
                exc_info=True
            )
            await session.rollback()
            raise

    async def _get_or_create_progress_record(self, session: AsyncSession, 
                                           user_id: int, achievement_type: AchievementType) -> AchievementProgress:
        """Получает или создает запись о прогрессе достижения"""
        try:
            result = await session.execute(
                select(AchievementProgress)
                .filter(
                    AchievementProgress.user_id == user_id,
                    AchievementProgress.achievement_type == achievement_type
                )
            )
            progress_record = result.scalars().first()
            
            if progress_record:
                logger.debug(
                    "Found existing progress record for user %d, achievement %s: %d",
                    user_id, achievement_type.name, progress_record.progress
                )
                return progress_record
            
            # Создаем новую запись
            progress_record = AchievementProgress(
                user_id=user_id,
                achievement_type=achievement_type,
                progress=0
            )
            session.add(progress_record)
            await session.commit()
            
            logger.info(
                "Created new progress record for user %d, achievement %s",
                user_id, achievement_type.name
            )
            
            return progress_record
            
        except Exception as e:
            logger.error(
                "Error getting/creating progress record for user %d, achievement %s: %s",
                user_id, achievement_type.name, str(e),
                exc_info=True
            )
            await session.rollback()
            raise

    async def check_session_achievements(self, user_id: int, session_data: Dict):
        """Проверяет все достижения, связанные с сессиями"""
        try:
            logger.info(
                "Checking session achievements for user %d, session data: %s",
                user_id, str(session_data)
            )
            
            # 1. Проверяем достижение за первую сессию
            logger.debug("Checking FIRST_SESSION achievement")
            await self.check_achievements(user_id, AchievementType.FIRST_SESSION)
            
            # 2. Проверяем общее количество сессий
            logger.debug("Checking SESSION_COUNT achievement")
            await self.check_achievements(user_id, AchievementType.SESSION_COUNT)
            
            # 3. Проверяем достижения, связанные с сопротивлением
            if session_data.get('resistance_level') == 'высокий':
                logger.debug("Checking HIGH_RESISTANCE achievement (high resistance)")
                await self.check_achievements(user_id, AchievementType.HIGH_RESISTANCE)
            
            # 4. Проверяем ежемесячный челлендж
            logger.debug("Checking MONTHLY_CHALLENGE achievement")
            await self.check_achievements(user_id, AchievementType.MONTHLY_CHALLENGE)
            
            # 5. Проверяем достижения, связанные с эмоциями
            if session_data.get('emotional'):
                logger.debug("Checking EMOTIONAL_EXPLORER achievement (emotional session)")
                await self.check_achievements(user_id, AchievementType.EMOTIONAL_EXPLORER, 1)
            
            # 6. Проверяем использование разных персон
            if session_data.get('persona_id'):
                logger.debug("Checking PERSONA_COLLECTOR achievement (persona used)")
                await self.check_achievements(user_id, AchievementType.PERSONA_COLLECTOR)
            
            # 7. Проверяем время суток (для Night Owl и Time Traveler)
            session_time = session_data.get('started_at')
            if session_time:
                hour = session_time.hour
                # Ночные сессии (00:00 - 05:00)
                if 0 <= hour < 5:
                    logger.debug(
                        "Checking NIGHT_OWL achievement (night session at %d:00)",
                        hour
                    )
                    await self.check_achievements(user_id, AchievementType.NIGHT_OWL, 1)
                
                # Для Time Traveler обновляем прогресс для текущего периода
                time_period = self._get_time_period(hour)
                logger.debug(
                    "Updating TIME_TRAVELER progress (time period: %s, hour: %d)",
                    time_period, hour
                )
                await self._update_time_traveler_progress(user_id, time_period)
            
            # 8. Проверяем день недели (для Weekend Warrior)
            if session_time and session_time.weekday() >= 5:
                logger.debug(
                    "Checking WEEKEND_WARRIOR achievement (weekend session)"
                )
                await self.check_achievements(user_id, AchievementType.WEEKEND_WARRIOR, 1)
            
            # 9. Проверяем последовательные дни (для Therapy Marathon)
            logger.debug("Checking THERAPY_MARATHON achievement (consecutive days)")
            await self._check_consecutive_days(user_id)
            
            logger.info("Completed checking session achievements for user %d", user_id)
            
        except Exception as e:
            logger.error(
                "Error checking session achievements for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
            
    async def _count_unique_emotions(self, session: AsyncSession, user_id: int) -> int:
        """Считает количество уникальных эмоций в сессиях пользователя"""
        try:
            result = await session.execute(
                select(func.count(func.distinct(Session.emotional)))
                .filter(
                    Session.user_id == user_id,
                    Session.emotional.isnot(None)
                )
            )
            count = result.scalar() or 0
            logger.debug("Found %d unique emotions for user %d", count, user_id)
            return count
        except Exception as e:
            logger.error(
                "Error counting unique emotions for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
            raise

    async def _update_time_traveler_progress(self, user_id: int, time_period: str):
        """Обновляет прогресс для Time Traveler с учетом нового периода"""
        try:
            async with self.sessionmaker() as session:
                # Получаем текущие покрытые периоды
                result = await session.execute(
                    select(AchievementProgress)
                    .filter(
                        AchievementProgress.user_id == user_id,
                        AchievementProgress.achievement_type == AchievementType.TIME_TRAVELER
                    )
                )
                progress_record = result.scalars().first()
                
                if not progress_record:
                    progress_record = AchievementProgress(
                        user_id=user_id,
                        achievement_type=AchievementType.TIME_TRAVELER,
                        progress=0
                    )
                    session.add(progress_record)
                    logger.debug(
                        "Created new TIME_TRAVELER progress record for user %d",
                        user_id
                    )
                
                # Получаем все сессии пользователя для определения покрытых периодов
                sessions = await session.execute(
                    select(Session.started_at)
                    .filter(Session.user_id == user_id)
                )
                sessions = sessions.scalars().all()
                
                periods_covered = set()
                for s in sessions:
                    periods_covered.add(self._get_time_period(s.hour))
                
                # Прогресс - количество уникальных периодов
                old_progress = progress_record.progress
                progress_record.progress = len(periods_covered)
                await session.commit()
                
                logger.debug(
                    "Updated TIME_TRAVELER progress for user %d: %d -> %d (periods: %s)",
                    user_id, old_progress, progress_record.progress, periods_covered
                )
                
        except Exception as e:
            logger.error(
                "Error updating TIME_TRAVELER progress for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
            raise

    async def _check_consecutive_days(self, user_id: int):
        """Проверяет последовательные дни с сессиями"""
        try:
            logger.debug(
                "Checking consecutive days for THERAPY_MARATHON, user %d",
                user_id
            )
            
            # Получаем даты сессий в отдельной короткой транзакции
            session_dates = await self._get_session_dates(user_id)
            
            if not session_dates:
                logger.debug("No session dates found for user %d", user_id)
                return
            
            logger.debug(
                "Found %d session dates for user %d: %s",
                len(session_dates), user_id, session_dates[:5]  # Логируем первые 5 дат
            )
            
            # Вычисляем максимальную последовательность дней
            max_consecutive = self._calculate_max_consecutive_days(session_dates)
            
            logger.debug(
                "Max consecutive days for user %d: %d",
                user_id, max_consecutive
            )
            
            # Обновляем прогресс в отдельной транзакции
            await self._update_therapy_marathon_progress(user_id, max_consecutive)
            
            # Проверяем достижения
            await self.check_achievements(user_id, AchievementType.THERAPY_MARATHON, 0)
            
        except Exception as e:
            logger.error(
                "Error checking consecutive days for user %d: %s",
                user_id, str(e),
                exc_info=True
            )

    async def _get_session_dates(self, user_id: int) -> List[datetime.date]:
        """Получает даты сессий пользователя"""
        try:
            async with self.sessionmaker() as session:
                result = await session.execute(
                    select(func.date(Session.started_at))
                    .filter(Session.user_id == user_id)
                    .group_by(func.date(Session.started_at))
                    .order_by(func.date(Session.started_at).asc())
                )
                dates = [datetime.datetime.strptime(d[0], '%Y-%m-%d').date() for d in result.all()]
                logger.debug(
                    "Retrieved %d unique session dates for user %d",
                    len(dates), user_id
                )
                return dates
        except Exception as e:
            logger.error(
                "Error getting session dates for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
            raise

    def _calculate_max_consecutive_days(self, session_dates: List[datetime.date]) -> int:
        """Вычисляет максимальное количество последовательных дней"""
        if not session_dates:
            logger.debug("Empty session dates list")
            return 0
            
        logger.debug(
            "Calculating max consecutive days from %d dates (%s to %s)",
            len(session_dates), session_dates[0], session_dates[-1]
        )
        
        max_consecutive = 1
        current_consecutive = 1
        prev_date = session_dates[0]
        
        for current_date in session_dates[1:]:
            delta = (current_date - prev_date).days
            
            if delta == 1:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            elif delta > 1:
                current_consecutive = 1
            
            prev_date = current_date
        
        logger.debug("Calculated max consecutive days: %d", max_consecutive)
        return max_consecutive

    async def _update_therapy_marathon_progress(self, user_id: int, max_consecutive: int):
        """Обновляет прогресс для Therapy Marathon"""
        try:
            async with self.sessionmaker() as session:
                progress_record = await self._get_or_create_progress_record(
                    session, user_id, AchievementType.THERAPY_MARATHON
                )
                
                if max_consecutive > progress_record.progress:
                    logger.debug(
                        "Updating THERAPY_MARATHON progress for user %d: %d -> %d",
                        user_id, progress_record.progress, max_consecutive
                    )
                    progress_record.progress = max_consecutive
                    await session.commit()
                else:
                    logger.debug(
                        "No progress update needed for THERAPY_MARATHON (current: %d, new: %d)",
                        progress_record.progress, max_consecutive
                    )
                    
        except Exception as e:
            logger.error(
                "Error updating THERAPY_MARATHON progress for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
            raise

    def _get_time_period(self, hour: int) -> str:
        """Определяет период дня по часам"""
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "night"
    
    async def check_feedback_achievements(self, user_id: int):
        """Проверяет достижения, связанные с обратной связью"""
        try:
            logger.info(
                "Checking FEEDBACK_CONTRIBUTOR achievement for user %d",
                user_id
            )
            await self.check_achievements(user_id, AchievementType.FEEDBACK_CONTRIBUTOR)
        except Exception as e:
            logger.error(
                "Error checking feedback achievements for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
    
    async def check_referral_achievements(self, user_id: int, new_referrals_count: int = 1):
        """Проверяет достижения, связанные с рефералами"""
        try:
            logger.info(
                "Checking REFERRAL_MASTER achievement for user %d (%d new referrals)",
                user_id, new_referrals_count
            )
            await self.check_achievements(
                user_id, 
                AchievementType.REFERRAL_MASTER, 
                new_referrals_count
            )
        except Exception as e:
            logger.error(
                "Error checking referral achievements for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
    
    async def get_user_achievements(self, user_id: int) -> Dict[AchievementType, List[Achievement]]:
        """Возвращает все достижения пользователя"""
        try:
            logger.debug("Getting all achievements for user %d", user_id)
            
            async with self.sessionmaker() as session:
                result = await session.execute(
                    select(Achievement)
                    .filter(Achievement.user_id == user_id)
                    .order_by(Achievement.awarded_at.desc())
                )
                achievements = result.scalars().all()
                
                grouped = defaultdict(list)
                for ach in achievements:
                    grouped[ach.badge_code].append(ach)
                
                logger.debug(
                    "Found %d achievements for user %d (%d types)",
                    len(achievements), user_id, len(grouped)
                )
                
                return dict(grouped)
                
        except Exception as e:
            logger.error(
                "Error getting achievements for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
            raise
    
    async def get_user_progress(self, user_id: int) -> Dict[AchievementType, Dict[str, Any]]:
        """Возвращает прогресс пользователя по всем достижениям"""
        try:
            logger.info("Getting progress for all achievements, user %d", user_id)
            result = {}
            
            async with self.sessionmaker() as session:
                # Получаем базовую статистику пользователя
                stats = await self._get_user_stats(session, user_id)
                logger.debug(
                    "Base stats for user %d: sessions=%d, high_resistance=%d, referrals=%d",
                    user_id, stats['session_count'], stats['high_resistance'], stats['referrals']
                )
                
                # Для каждого типа достижения определяем прогресс
                for ach_type in AchievementType:
                    progress_info = await self._get_progress_info(session, user_id, ach_type, stats)
                    result[ach_type] = progress_info
                    logger.debug(
                        "Progress for user %d, achievement %s: %s",
                        user_id, ach_type.name, str(progress_info)
                    )
            
            return result
            
        except Exception as e:
            logger.error(
                "Error getting user progress for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
            raise

    async def _get_user_stats(self, session: AsyncSession, user_id: int) -> Dict[str, int]:
        """Получает базовую статистику пользователя"""
        try:
            logger.debug("Getting base stats for user %d", user_id)
            
            session_count = (await session.execute(
                select(func.count()).select_from(Session)
                .filter(Session.user_id == user_id)
            )).scalar() or 0
            
            high_resistance = (await session.execute(
                select(func.count()).select_from(Session)
                .filter(
                    Session.user_id == user_id,
                    Session.resistance_level == 'высокий'
                )
            )).scalar() or 0
            
            referrals = (await session.execute(
                select(func.count()).select_from(Referral)
                .filter(Referral.inviter_id == user_id)
            )).scalar() or 0
            
            return {
                'session_count': session_count,
                'high_resistance': high_resistance,
                'referrals': referrals
            }
            
        except Exception as e:
            logger.error(
                "Error getting user stats for user %d: %s",
                user_id, str(e),
                exc_info=True
            )
            raise

    async def _get_progress_info(self, session: AsyncSession, user_id: int, 
                               ach_type: AchievementType, stats: Dict[str, int]) -> Dict[str, Any]:
        """Формирует информацию о прогрессе для конкретного типа достижения"""
        try:
            logger.debug(
                "Getting progress info for user %d, achievement %s",
                user_id, ach_type.name
            )
            
            progress_info = {
                'current_tier': None,
                'next_tier': None,
                'current_progress': 0,
                'next_progress_required': 0
            }
            
            # Определяем текущий прогресс
            progress_info['current_progress'] = await self._get_current_progress(
                session, user_id, ach_type, stats
            )
            
            logger.debug(
                "Current progress for user %d, achievement %s: %d",
                user_id, ach_type.name, progress_info['current_progress']
            )
            
            # Получаем конфигурацию достижения
            config = self.achievement_config.get(ach_type, {})
            
            # Определяем текущий и следующий уровень
            achieved_tiers = await self._get_achieved_tiers(session, user_id, ach_type)
            logger.debug(
                "Achieved tiers for user %d, achievement %s: %s",
                user_id, ach_type.name, [t.name for t in achieved_tiers]
            )
            
            for tier in [AchievementTier.PLATINUM, AchievementTier.GOLD, 
                        AchievementTier.SILVER, AchievementTier.BRONZE]:
                if tier in config and tier in achieved_tiers:
                    progress_info['current_tier'] = tier
                    break
            
            # Определяем следующий уровень
            if config:
                tiers = list(config.keys())
                if progress_info['current_tier']:
                    current_idx = tiers.index(progress_info['current_tier'])
                    if current_idx + 1 < len(tiers):
                        next_tier = tiers[current_idx + 1]
                        progress_info['next_tier'] = next_tier
                        progress_info['next_progress_required'] = config[next_tier]['required']
                else:
                    progress_info['next_tier'] = tiers[0]
                    progress_info['next_progress_required'] = config[tiers[0]]['required']
            
            logger.debug(
                "Progress info for user %d, achievement %s: %s",
                user_id, ach_type.name, progress_info
            )
            
            return progress_info
            
        except Exception as e:
            logger.error(
                "Error getting progress info for user %d, achievement %s: %s",
                user_id, ach_type.name, str(e),
                exc_info=True
            )
            raise

    async def _get_current_progress(self, session: AsyncSession, user_id: int, 
                                  ach_type: AchievementType, stats: Dict[str, int]) -> int:
        """Получает текущий прогресс для типа достижения"""
        try:
            logger.debug(
                "Getting current progress for user %d, achievement %s",
                user_id, ach_type.name
            )
            
            if ach_type == AchievementType.SESSION_COUNT:
                return stats['session_count']
            elif ach_type == AchievementType.HIGH_RESISTANCE:
                return stats['high_resistance']
            elif ach_type == AchievementType.REFERRAL_MASTER:
                return stats['referrals']
            elif ach_type == AchievementType.MONTHLY_CHALLENGE:
                now = datetime.datetime.utcnow()
                count = (await session.execute(
                    select(func.count()).select_from(Session)
                    .filter(
                        Session.user_id == user_id,
                        extract('month', Session.started_at) == now.month,
                        extract('year', Session.started_at) == now.year
                    )
                )).scalar() or 0
                logger.debug(
                    "Monthly challenge progress for user %d: %d (%d-%d)",
                    user_id, count, now.month, now.year
                )
                return count
            elif ach_type == AchievementType.PERSONA_COLLECTOR:
                count = (await session.execute(
                    select(func.count(func.distinct(Session.persona_id)))
                    .filter(
                        Session.user_id == user_id,
                        Session.persona_id.isnot(None)
                    )
                )).scalar() or 0
                logger.debug("Persona collector progress for user %d: %d", user_id, count)
                return count
            elif ach_type == AchievementType.EMOTIONAL_EXPLORER:
                count = await self._count_unique_emotions(session, user_id)
                logger.debug("Unique emotions count for user %d: %d", user_id, count)
                return count
            else:
                progress_result = await session.execute(
                    select(AchievementProgress.progress)
                    .filter(
                        AchievementProgress.user_id == user_id,
                        AchievementProgress.achievement_type == ach_type
                    )
                )
                progress = progress_result.scalar() or 0
                logger.debug(
                    "Progress for user %d, achievement %s: %d",
                    user_id, ach_type.name, progress
                )
                return progress
                
        except Exception as e:
            logger.error(
                "Error getting current progress for user %d, achievement %s: %s",
                user_id, ach_type.name, str(e),
                exc_info=True
            )
            raise

    async def _get_achieved_tiers(self, session: AsyncSession, 
                                 user_id: int, ach_type: AchievementType) -> set:
        """Получает полученные уровни для типа достижения"""
        try:
            result = await session.execute(
                select(Achievement.tier)
                .filter(
                    Achievement.user_id == user_id,
                    Achievement.badge_code == ach_type
                )
            )
            tiers = {a[0] for a in result.all()}
            logger.debug(
                "Achieved tiers for user %d, achievement %s: %s",
                user_id, ach_type.name, [t.name for t in tiers]
            )
            return tiers
        except Exception as e:
            logger.error(
                "Error getting achieved tiers for user %d, achievement %s: %s",
                user_id, ach_type.name, str(e),
                exc_info=True
            )
            raise