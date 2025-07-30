from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from typing import Dict, List, Optional, Any
import datetime
from enum import Enum
import logging
from collections import defaultdict
from database.models import Achievement, User, Session, AchievementType, AchievementTier, Referral
from sqlalchemy.ext.asyncio import AsyncSession
from config import logger
from sqlalchemy.future import select
from sqlalchemy import func

class AchievementSystem:
    def __init__(self, bot, engine):
        self.bot = bot
        self.engine = engine
        self.async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        # Конфигурация достижений: требования для каждого уровня
        self.achievement_config = {
            AchievementType.FIRST_SESSION: {
                AchievementTier.BRONZE: {'required': 1, 'points': 10}
            },
            AchievementType.SESSION_COUNT: {
                AchievementTier.BRONZE: {'required': 5, 'points': 20},
                AchievementTier.SILVER: {'required': 20, 'points': 50},
                AchievementTier.GOLD: {'required': 50, 'points': 100},
                AchievementTier.PLATINUM: {'required': 100, 'points': 200}
            },
            AchievementType.HIGH_RESISTANCE: {
                AchievementTier.BRONZE: {'required': 3, 'points': 30},
                AchievementTier.SILVER: {'required': 10, 'points': 70},
                AchievementTier.GOLD: {'required': 25, 'points': 150}
            },
            AchievementType.MONTHLY_CHALLENGE: {
                AchievementTier.BRONZE: {'required': 5, 'points': 30},
                AchievementTier.SILVER: {'required': 10, 'points': 70},
                AchievementTier.GOLD: {'required': 20, 'points': 150}
            },
            AchievementType.EMOTIONAL_EXPLORER: {
                AchievementTier.BRONZE: {'required': 3, 'points': 20},
                AchievementTier.SILVER: {'required': 10, 'points': 50},
                AchievementTier.GOLD: {'required': 20, 'points': 100}
            },
            AchievementType.PERSONA_COLLECTOR: {
                AchievementTier.BRONZE: {'required': 3, 'points': 30},
                AchievementTier.SILVER: {'required': 7, 'points': 70},
                AchievementTier.GOLD: {'required': 12, 'points': 150}
            },
            AchievementType.THERAPY_MARATHON: {
                AchievementTier.BRONZE: {'required': 3, 'points': 30},  # 3 дня подряд
                AchievementTier.SILVER: {'required': 7, 'points': 70},  # 7 дней подряд
                AchievementTier.GOLD: {'required': 30, 'points': 200}   # 30 дней подряд
            },
            AchievementType.FEEDBACK_CONTRIBUTOR: {
                AchievementTier.BRONZE: {'required': 1, 'points': 10},
                AchievementTier.SILVER: {'required': 3, 'points': 30},
                AchievementTier.GOLD: {'required': 10, 'points': 100}
            },
            AchievementType.NIGHT_OWL: {
                AchievementTier.BRONZE: {'required': 3, 'points': 20},
                AchievementTier.SILVER: {'required': 10, 'points': 50},
                AchievementTier.GOLD: {'required': 20, 'points': 100}
            },
            AchievementType.WEEKEND_WARRIOR: {
                AchievementTier.BRONZE: {'required': 3, 'points': 20},
                AchievementTier.SILVER: {'required': 10, 'points': 50},
                AchievementTier.GOLD: {'required': 20, 'points': 100}
            },
            AchievementType.EMOTION_MASTER: {
                AchievementTier.BRONZE: {'required': 5, 'points': 30},
                AchievementTier.SILVER: {'required': 15, 'points': 70},
                AchievementTier.GOLD: {'required': 30, 'points': 150}
            },
            AchievementType.TIME_TRAVELER: {
                AchievementTier.BRONZE: {'required': 4, 'points': 30},  # Все периоды дня
                AchievementTier.SILVER: {'required': 10, 'points': 70}, # 10 раз все периоды
                AchievementTier.GOLD: {'required': 30, 'points': 150}  # 30 раз все периоды
            },
            AchievementType.REFERRAL_MASTER: {
                AchievementTier.BRONZE: {'required': 1, 'points': 20},
                AchievementTier.SILVER: {'required': 5, 'points': 100},
                AchievementTier.GOLD: {'required': 10, 'points': 200}
            }
        }
    
    async def check_achievements(self, user_id: int, achievement_type: AchievementType, progress_increment: int = 1) -> List[Achievement]:
        """Проверяет и обновляет достижения пользователя"""
        async with self.async_session() as session:
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
                
                # Получаем текущий прогресс
                current_progress = defaultdict(int)
                for ach in user_achievements:
                    current_progress[ach.tier] = ach.progress
                
                # Получаем конфигурацию для этого типа достижения
                config = self.achievement_config.get(achievement_type, {})
                new_achievements = []
                
                # Проверяем каждый уровень достижения
                for tier, requirements in config.items():
                    required = requirements['required']
                    points = requirements['points']
                    
                    # Если у пользователя уже есть этот уровень, пропускаем
                    if any(ach.tier == tier for ach in user_achievements):
                        continue
                    
                    # Обновляем прогресс
                    progress = current_progress.get(tier, 0) + progress_increment
                    
                    # Если прогресс достиг или превысил требуемое значение
                    if progress >= required:
                        # Создаем новое достижение
                        new_ach = Achievement(
                            user_id=user_id,
                            badge_code=achievement_type,
                            tier=tier,
                            progress=100,
                            points=points,
                            awarded_at=datetime.datetime.utcnow()
                        )
                        session.add(new_ach)
                        new_achievements.append(new_ach)
                        
                        # Отправляем уведомление пользователю
                        await self._notify_user(user_id, achievement_type, tier)
                
                await session.commit()
                return new_achievements
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Error checking achievements: {e}", exc_info=True)
                return []
    
    async def _notify_user(self, user_id: int, achievement_type: AchievementType, tier: AchievementTier):
        """Отправляет уведомление пользователю о новом достижении"""
        try:
            async with self.async_session() as session:
                result = await session.execute(
                    select(User).filter(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    return
                
                # Формируем сообщение
                achievement_name = self._get_achievement_name(achievement_type)
                tier_name = self._get_tier_name(tier)
                
                message = (
                    f"🎉 Поздравляем! Вы получили достижение!\n\n"
                    f"🏆 <b>{achievement_name} ({tier_name})</b>\n\n"
                    f"Продолжайте в том же духе!"
                )
                
                # Отправляем сообщение
                await self.bot.send_message(chat_id=user.telegram_id, text=message, parse_mode='HTML')
                
        except Exception as e:
            logger.error(f"Error notifying user about achievement: {e}")
    
    def _get_achievement_name(self, achievement_type: AchievementType) -> str:
        """Возвращает читаемое название достижения"""
        names = {
            AchievementType.FIRST_SESSION: "Первая сессия",
            AchievementType.SESSION_COUNT: "Количество сессий",
            AchievementType.HIGH_RESISTANCE: "Высокое сопротивление",
            AchievementType.MONTHLY_CHALLENGE: "Ежемесячный челлендж",
            AchievementType.EMOTIONAL_EXPLORER: "Исследователь эмоций",
            AchievementType.PERSONA_COLLECTOR: "Коллекционер персон",
            AchievementType.THERAPY_MARATHON: "Марафон терапии",
            AchievementType.FEEDBACK_CONTRIBUTOR: "Контрибьютор обратной связи",
            AchievementType.NIGHT_OWL: "Ночная сова",
            AchievementType.WEEKEND_WARRIOR: "Воитель выходного дня",
            AchievementType.EMOTION_MASTER: "Мастер эмоций",
            AchievementType.TIME_TRAVELER: "Путешественник во времени",
            AchievementType.REFERRAL_MASTER: "Мастер приглашений"
        }
        return names.get(achievement_type, "Достижение")
    
    def _get_tier_name(self, tier: AchievementTier) -> str:
        """Возвращает читаемое название уровня достижения"""
        names = {
            AchievementTier.BRONZE: "Бронза",
            AchievementTier.SILVER: "Серебро",
            AchievementTier.GOLD: "Золото",
            AchievementTier.PLATINUM: "Платина"
        }
        return names.get(tier, "")
    
    async def check_session_achievements(self, user_id: int, session_data: Dict):
        """Проверяет все достижения, связанные с сессиями"""
        try:
            # 1. Проверяем достижение за первую сессию
            await self.check_achievements(user_id, AchievementType.FIRST_SESSION)
            
            # 2. Проверяем общее количество сессий
            await self.check_achievements(user_id, AchievementType.SESSION_COUNT)
            
            # 3. Проверяем достижения, связанные с сопротивлением
            if session_data.get('resistance_level') == 'high':
                await self.check_achievements(user_id, AchievementType.HIGH_RESISTANCE)
            
            # 4. Проверяем достижения, связанные с эмоциями
            if session_data.get('emotional'):
                await self.check_achievements(user_id, AchievementType.EMOTIONAL_EXPLORER)
            
            # 5. Проверяем использование разных персон
            if session_data.get('persona_id'):
                await self.check_achievements(user_id, AchievementType.PERSONA_COLLECTOR)
            
            # 6. Проверяем время суток (для Night Owl и Time Traveler)
            session_time = session_data.get('started_at')
            if session_time:
                hour = session_time.hour
                # Ночные сессии (00:00 - 05:00)
                if 0 <= hour < 5:
                    await self.check_achievements(user_id, AchievementType.NIGHT_OWL)
                
                # Проверяем все периоды дня для Time Traveler
                period = self._get_time_period(hour)
                await self.check_achievements(user_id, AchievementType.TIME_TRAVELER)
            
            # 7. Проверяем день недели (для Weekend Warrior)
            if session_time and session_time.weekday() >= 5:  # Суббота или воскресенье
                await self.check_achievements(user_id, AchievementType.WEEKEND_WARRIOR)
            
            # 8. Проверяем последовательные дни (для Therapy Marathon)
            await self._check_consecutive_days(user_id)
            
        except Exception as e:
            logger.error(f"Error checking session achievements: {e}")
    
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
    
    async def _check_consecutive_days(self, user_id: int):
        """Проверяет последовательные дни с сессиями"""
        async with self.async_session() as session:
            try:
                # Получаем все сессии пользователя, отсортированные по дате
                result = await session.execute(
                    select(Session)
                    .filter(Session.user_id == user_id)
                    .order_by(Session.started_at)
                )
                sessions = result.scalars().all()
                
                if not sessions:
                    return
                
                # Считаем максимальную последовательность дней подряд с сессиями
                max_consecutive = 1
                current_consecutive = 1
                prev_date = sessions[0].started_at.date()
                
                for session in sessions[1:]:
                    current_date = session.started_at.date()
                    delta = (current_date - prev_date).days
                    
                    if delta == 1:  # Последовательные дни
                        current_consecutive += 1
                        if current_consecutive > max_consecutive:
                            max_consecutive = current_consecutive
                    elif delta > 1:  # Разрыв в последовательности
                        current_consecutive = 1
                    
                    prev_date = current_date
                
                # Проверяем достижения Therapy Marathon
                if max_consecutive >= 3:
                    progress = min(max_consecutive, 30)  # Максимум 30 для плато
                    await self.check_achievements(
                        user_id, 
                        AchievementType.THERAPY_MARATHON, 
                        progress_increment=progress
                    )
                
            except Exception as e:
                logger.error(f"Error checking consecutive days: {e}")
    
    async def check_feedback_achievements(self, user_id: int):
        """Проверяет достижения, связанные с обратной связью"""
        await self.check_achievements(user_id, AchievementType.FEEDBACK_CONTRIBUTOR)
    
    async def check_referral_achievements(self, user_id: int, new_referrals_count: int = 1):
        """Проверяет достижения, связанные с рефералами"""
        await self.check_achievements(
            user_id, 
            AchievementType.REFERRAL_MASTER, 
            progress_increment=new_referrals_count
        )
    
    async def get_user_achievements(self, user_id: int) -> Dict[AchievementType, List[Achievement]]:
        """Возвращает все достижения пользователя, сгруппированные по типу"""
        async with self.async_session() as session:
            result = await session.execute(
                select(Achievement)
                .filter(Achievement.user_id == user_id)
                .order_by(Achievement.awarded_at.desc())
            )
            achievements = result.scalars().all()
            
            grouped = defaultdict(list)
            for ach in achievements:
                grouped[ach.badge_code].append(ach)
            
            return dict(grouped)
    
    async def get_user_progress(self, user_id: int) -> Dict[AchievementType, Dict[str, Any]]:
        """Возвращает прогресс пользователя по всем достижениям"""
        result = {}
        async with self.async_session() as session:
            # Получаем статистику пользователя
            session_count = (await session.execute(
                select(func.count()).select_from(Session)
                .filter(Session.user_id == user_id)
            )).scalar()
            
            high_resistance = (await session.execute(
                select(func.count()).select_from(Session)
                .filter(
                    Session.user_id == user_id,
                    Session.resistance_level == 'high'
                )
            )).scalar()
            
            referrals = (await session.execute(
                select(func.count()).select_from(Referral)
                .filter(Referral.inviter_id == user_id)
            )).scalar()
            
            # Для каждого типа достижения определяем прогресс
            for ach_type in AchievementType:
                progress_info = {
                    'current_tier': None,
                    'next_tier': None,
                    'current_progress': 0,
                    'next_progress_required': 0
                }
                
                # Определяем текущий прогресс
                if ach_type == AchievementType.SESSION_COUNT:
                    progress_info['current_progress'] = session_count or 0
                elif ach_type == AchievementType.HIGH_RESISTANCE:
                    progress_info['current_progress'] = high_resistance or 0
                elif ach_type == AchievementType.REFERRAL_MASTER:
                    progress_info['current_progress'] = referrals or 0
                
                # Определяем текущий и следующий уровень
                config = self.achievement_config.get(ach_type, {})
                
                # Получаем достижения пользователя этого типа
                achievements_result = await session.execute(
                    select(Achievement)
                    .filter(
                        Achievement.user_id == user_id,
                        Achievement.badge_code == ach_type
                    )
                )
                achieved = achievements_result.scalars().all()
                
                achieved_tiers = {a.tier for a in achieved}
                for tier in [AchievementTier.PLATINUM, AchievementTier.GOLD, 
                            AchievementTier.SILVER, AchievementTier.BRONZE]:
                    if tier in config and tier in achieved_tiers:
                        progress_info['current_tier'] = tier
                        break
                
                # Определяем следующий уровень
                if progress_info['current_tier']:
                    tiers = list(config.keys())
                    current_idx = tiers.index(progress_info['current_tier'])
                    if current_idx + 1 < len(tiers):
                        progress_info['next_tier'] = tiers[current_idx + 1]
                        progress_info['next_progress_required'] = config[progress_info['next_tier']]['required']
                else:
                    if config:
                        progress_info['next_tier'] = list(config.keys())[0]
                        progress_info['next_progress_required'] = config[progress_info['next_tier']]['required']
                
                result[ach_type] = progress_info
        
        return result