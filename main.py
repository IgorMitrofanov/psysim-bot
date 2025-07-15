import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import config, DEFAULT_BOT_PROPERTIES
from database.models import Base
from handlers import routers
from middlewares.db import DBSessionMiddleware

async def init_db():
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
    
    for router in routers:
        dp.include_router(router)
    
    try:
        await dp.start_polling(bot)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())