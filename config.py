import os
from dotenv import load_dotenv
import logging
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

load_dotenv()

# --- Config ---
class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot_db.sqlite")
    AI_API_KEY = os.getenv("AI_API_KEY")
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL")
    SESSION_LENGTH_MINUTES = os.getenv("SESSION_LENGTH_MINUTES")
    WARNING_BEFORE_END_MINUTES = int(os.getenv("WARNING_BEFORE_END_MINUTES", 5))
    LOG_LEVEL = int(os.getenv("LOG_LEVEL", 20))  # 20 = INFO, 10 = DEBUG
    _quota_str = os.getenv("TARIFF_QUOTAS_STR", "trial:1,start:3,pro:10,unlimited:999999")
    _tariff_str = os.getenv("TARIFFS", "")
    TARIFF_MAP = {}
    TARIFF_QUOTAS = {}

    if _tariff_str:
        for item in _tariff_str.split(","):
            try:
                key, price, days, quota = item.split(":")
                TARIFF_MAP[key] = (key, int(price), int(days), int(quota))
                TARIFF_QUOTAS[key] = int(quota)
            except ValueError:
                print(f"Ошибка парсинга тарифа: {item}")

config = Config()

# --- Logging ---
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main-logger")

# --- Bot Default Properties ---
DEFAULT_BOT_PROPERTIES = DefaultBotProperties(parse_mode=ParseMode.HTML)
