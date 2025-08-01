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

    # PAYMENT_SHOP_ID = int(os.getenv("PAYMENT_SHOP_ID"))
    # PAYMENT_SECRET_KEY = os.getenv("PAYMENT_SECRET_KEY")

    PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
    CURRENCY = os.getenv("CURRENCY", "RUB")
    
    @property
    def provider_data_template(self):
        return {
            "receipt": {
                "items": [
                    {
                        "description": "Подписка на тариф",
                        "quantity": "1.00",
                        "amount": {
                            "value": "0.00",  # Будем переопределять
                            "currency": self.CURRENCY
                        },
                        "vat_code": 1
                    }
                ]
            }
        }



config = Config()

# --- Logging ---
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main-logger")

# --- Bot Default Properties ---
DEFAULT_BOT_PROPERTIES = DefaultBotProperties(parse_mode=ParseMode.HTML)
