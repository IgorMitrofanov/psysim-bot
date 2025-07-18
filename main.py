import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import config, DEFAULT_BOT_PROPERTIES, logger
from database.models import Base
from handlers import routers
from middlewares.db import DBSessionMiddleware
from core.session_manager import SessionManager

async def init_db():
    logger.debug("database init")
    engine = create_async_engine(config.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine

async def main():
    engine = await init_db()
    bot = Bot(token=config.BOT_TOKEN, default=DEFAULT_BOT_PROPERTIES)  
    dp = Dispatcher(storage=MemoryStorage())
    
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    dp.message.middleware(DBSessionMiddleware(sessionmaker))
    dp.callback_query.middleware(DBSessionMiddleware(sessionmaker))
    
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