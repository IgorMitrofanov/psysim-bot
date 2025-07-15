# bot/database/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models import User

async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str = None) -> User:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
    
    return user