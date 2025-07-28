import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine
from services.subscription_checker import check_subscriptions_expiry
from config import config, DEFAULT_BOT_PROPERTIES, logger
from database.models import Base
from handlers import routers
import ssl
from middlewares.db import DBSessionMiddleware
from services.session_manager import SessionManager
from pathlib import Path
import aiohttp
from aiogram.types import BotCommand
from typing import Tuple

async def set_default_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="Начать работу / перейти в главное меню"),
    ]
    await bot.set_my_commands(commands)
    
async def on_startup(bot: Bot):
    await set_default_commands(bot)

async def download_ssl_cert():
    cert_dir = Path.home() / ".cloud-certs"
    cert_path = cert_dir / "root.crt"
    cert_dir.mkdir(parents=True, exist_ok=True)
    
    if not cert_path.exists():
        cert_url = "https://st.timeweb.com/cloud-static/ca.crt"
        async with aiohttp.ClientSession() as session:
            async with session.get(cert_url) as response:
                if response.status == 200:
                    with open(cert_path, 'wb') as f:
                        f.write(await response.read())
                    cert_path.chmod(0o600)
                    logger.info(f"SSL certificate downloaded to {cert_path}")
                else:
                    logger.error(f"Failed to download SSL certificate from {cert_url}")
                    raise Exception("SSL certificate download failed")
    return cert_path

async def init_db() -> Tuple[AsyncEngine, AsyncEngine]:
    """Инициализирует 2 движка: 
    - default_engine (DATABASE_URL) — для всех таблиц, кроме персонажей
    - admin_engine (ADMIN_DATABASE_URL) — только для персонажей
    """
    cert_path = await download_ssl_cert()
    ssl_ctx = ssl.create_default_context(cafile=cert_path)
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED

    # Движок для основных таблиц (пользователи, сессии и т.д.)
    default_engine = create_async_engine(
        config.DATABASE_URL,
        # connect_args={"ssl": ssl_ctx},
        # pool_pre_ping=True,
        # echo=False,
    )

    # Движок только для персонажей (админский доступ)
    admin_engine = create_async_engine(
        config.ADMIN_DATABASE_URL,
        # connect_args={"ssl": ssl_ctx},
        # pool_pre_ping=True,
        # echo=False,
    )

    # Создаем таблицы в основной БД (default_engine)
    async with default_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database engines initialized")
    return default_engine, admin_engine

async def main():
    # Инициализация двух движков
    default_engine, admin_engine = await init_db()
    
    bot = Bot(token=config.BOT_TOKEN, default=DEFAULT_BOT_PROPERTIES)  
    dp = Dispatcher(storage=MemoryStorage())
    
    # Запускаем миграцию персонажей перед стартом бота
    from migrate_personas import migrate_personas
    logger.info("Starting personas migration...")
    await migrate_personas()
    logger.info("Personas migration completed successfully")

    # Сессии для основных таблиц (default_engine)
    sessionmaker = async_sessionmaker(default_engine, expire_on_commit=False)
    dp.message.middleware(DBSessionMiddleware(sessionmaker))
    dp.callback_query.middleware(DBSessionMiddleware(sessionmaker))

    dp.startup.register(on_startup)
    asyncio.create_task(check_subscriptions_expiry(bot, sessionmaker))

    # Инициализация менеджера сессий (передаем оба движка)
    session_manager = SessionManager(bot, admin_engine=admin_engine)
    dp['session_manager'] = session_manager
    
    for router in routers:
        logger.debug(f"router {router.name} init")
        dp.include_router(router)
    
    try:
        logger.info("Start polling")
        await dp.start_polling(bot)
    finally:
        logger.info("Cleaning up")
        await session_manager.cleanup()
        await default_engine.dispose()
        await admin_engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())