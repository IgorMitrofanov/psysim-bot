# bot/config.py
import os
from dotenv import load_dotenv
import logging
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

load_dotenv()

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Config ---
class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot_db.sqlite")
    AI_API_KEY = os.getenv("AI_API_KEY")
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL")
    SESSION_LENGTH_MINUTES = os.getenv("SESSION_LENGTH_MINUTES")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
config = Config()

# --- Bot Default Properties ---
DEFAULT_BOT_PROPERTIES = DefaultBotProperties(parse_mode=ParseMode.HTML)