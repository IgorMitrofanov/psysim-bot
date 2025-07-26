import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from services.subscription_checker import check_subscriptions_expiry
from config import config, DEFAULT_BOT_PROPERTIES, logger
from database.models import Base
from handlers import routers
import ssl
from middlewares.db import DBSessionMiddleware
from services.session_manager import SessionManager
from pathlib import Path
import aiohttp

async def download_ssl_cert():
    cert_dir = Path.home() / ".cloud-certs"
    cert_path = cert_dir / "root.crt"
    
    # Создаем директорию, если ее нет
    cert_dir.mkdir(parents=True, exist_ok=True)
    
    # Скачиваем сертификат, если его нет
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

async def init_db():
    logger.debug("database init")
    cert_path = await download_ssl_cert()
    # Создаем SSL контекст для подключения
    ssl_ctx = ssl.create_default_context(cafile=cert_path)
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED  # Аналог verify-full
    
    engine = create_async_engine(
        config.DATABASE_URL,
        connect_args={
            "ssl": ssl_ctx,
        },
        pool_pre_ping=True,  # Проверка соединения перед использованием
        echo=False,          # Логирование SQL запросов (False для продакшена)
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine

# Установка сертификата
# mkdir -p ~/.cloud-certs && \
# curl -o ~/.cloud-certs/root.crt "https://st.timeweb.com/cloud-static/ca.crt" && \
# chmod 0600 ~/.cloud-certs/root.crt
# export PGSSLROOTCERT=$HOME/.cloud-certs/root.crt


async def main():
    engine = await init_db()
    bot = Bot(token=config.BOT_TOKEN, default=DEFAULT_BOT_PROPERTIES)  
    dp = Dispatcher(storage=MemoryStorage()) # заменить на реддис например
    
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    dp.message.middleware(DBSessionMiddleware(sessionmaker))
    dp.callback_query.middleware(DBSessionMiddleware(sessionmaker))
    
    # Фоновая задача по проверке подписок
    asyncio.create_task(check_subscriptions_expiry(bot, sessionmaker))
    # Инициализация менеджера сессий
    session_manager = SessionManager(bot)
    dp['session_manager'] = session_manager
    
    
    for router in routers:
        logger.debug(f"router {router.name} init")
        dp.include_router(router)
    
    try:
        logger.info("Start polling")
        await dp.start_polling(bot)
    finally:
        logger.info("terminate database process")
        await session_manager.cleanup()
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())