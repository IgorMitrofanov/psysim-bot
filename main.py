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

async def check_stale_sessions(bot: Bot, sessionmaker):
    """Периодическая проверка зависших сессий"""
    while True:
        try:
            async with sessionmaker() as session:
                session_manager = SessionManager(bot)
                # Находим сессии, которые должны были закончиться
                stmt = """
                UPDATE sessions 
                SET is_active = FALSE 
                WHERE is_active = TRUE AND expires_at < NOW()
                RETURNING user_id
                """
                result = await session.execute(stmt)
                expired_sessions = result.scalars().all()
                
                for user_id in expired_sessions:
                    await session_manager.notify_session_end(user_id)
                
                await session.commit()
                
        except Exception as e:
            logger.error(f"Error in stale sessions check: {e}")
        
        await asyncio.sleep(60 * 5)  # Проверяем каждые 5 минут

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
    
    # Запуск фоновой задачи для проверки сессий
    asyncio.create_task(check_stale_sessions(bot, sessionmaker))
    
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