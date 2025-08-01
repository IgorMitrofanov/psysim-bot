from database.models import AchievementType, AchievementTier


ach_config = {
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
                AchievementTier.SILVER: {'required': 12, 'points': 70},
                AchievementTier.GOLD: {'required': 25, 'points': 150}
            },
            AchievementType.MONTHLY_CHALLENGE: {
                AchievementTier.BRONZE: {'required': 5, 'points': 30},
                AchievementTier.SILVER: {'required': 10, 'points': 70},
                AchievementTier.GOLD: {'required': 20, 'points': 150}
            },
            AchievementType.EMOTIONAL_EXPLORER: {
                AchievementTier.BRONZE: {'required': 2, 'points': 20},
                AchievementTier.SILVER: {'required': 4, 'points': 50},
                AchievementTier.GOLD: {'required': 6, 'points': 100}
            },
            AchievementType.PERSONA_COLLECTOR: {
                AchievementTier.BRONZE: {'required': 3, 'points': 30},
                AchievementTier.SILVER: {'required': 7, 'points': 70},
                # AchievementTier.GOLD: {'required': 12, 'points': 150} # больше 7 пока нет
            },
            AchievementType.THERAPY_MARATHON: {
                AchievementTier.BRONZE: {'required': 3, 'points': 30},
                AchievementTier.SILVER: {'required': 7, 'points': 70},
                AchievementTier.GOLD: {'required': 30, 'points': 200}
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
            AchievementType.TIME_TRAVELER: {
                AchievementTier.BRONZE: {'required': 4, 'points': 30},
                AchievementTier.SILVER: {'required': 10, 'points': 70},
                AchievementTier.GOLD: {'required': 30, 'points': 150}
            },
            AchievementType.REFERRAL_MASTER: {
                AchievementTier.BRONZE: {'required': 1, 'points': 20},
                AchievementTier.SILVER: {'required': 5, 'points': 100},
                AchievementTier.GOLD: {'required': 10, 'points': 200}
            }
        }

ach_names = {
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
            AchievementType.TIME_TRAVELER: "Путешественник во времени",
            AchievementType.REFERRAL_MASTER: "Мастер приглашений"
        }