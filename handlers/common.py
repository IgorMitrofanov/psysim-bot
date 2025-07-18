from uuid import uuid4
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_user, create_user, get_user_by_id, get_user_by_referral_code
)
from keyboards.builder import main_menu
from states import MainMenu
from texts.common import get_start_text, BACK_TO_MENU_TEXT
from config import logger
from datetime import datetime
from database.models import Referral, User
router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        from_user = message.from_user
        logger.debug(f"Start command from: {from_user.id}")

        text_parts = message.text.split()
        referrer = None
        
        # Обработка рефералки
        if len(text_parts) > 1 and text_parts[1].startswith("ref_"):
            try:
                referral_code = text_parts[1].split("_")[1]
                logger.debug(f"Processing referral code: {referral_code}")

                # Ищем реферера по коду
                referrer = await session.execute(
                    select(User)
                    .where(User.referral_code == referral_code)
                    .execution_options(populate_existing=True)
                ).scalar_one_or_none()
                
                if referrer:
                    logger.info(f"Referrer found: {referrer.telegram_id}")
                else:
                    logger.warning(f"Referrer with code {referral_code} not found")
                    
            except Exception as e:
                logger.error(f"Error processing referral: {e}")

        # Получаем или создаем пользователя
        db_user = await get_user(session, telegram_id=from_user.id)
        is_new_user = False
        
        if db_user is None:
            # Генерируем уникальный реферальный код
            while True:
                new_referral_code = str(uuid4())[:8]
                existing_user = await get_user_by_referral_code(session, new_referral_code)
                if not existing_user:
                    break

            db_user = await create_user(
                session=session,
                telegram_id=from_user.id,
                username=from_user.username,
                language_code=from_user.language_code,
                is_premium=from_user.is_premium,
                referred_by_id=referrer.id if referrer else None,
                referral_code=new_referral_code,
            )
            logger.info(f"New user created with ID: {db_user.id}")
            is_new_user = True

            # Если есть реферер, создаем запись в таблице Referral
            if referrer:
                try:
                    # Создаем запись о реферале
                    referral = Referral(
                        invited_user_id=db_user.id,
                        inviter_id=referrer.id,
                        joined_at=datetime.utcnow()
                    )
                    session.add(referral)
                    
                    # Начисляем бонус рефереру
                    referrer.bonus_balance += 1
                    await session.commit()
                    
                    logger.info(f"Added bonus to referrer {referrer.telegram_id}. New balance: {referrer.bonus_balance}")
                    
                    # Отправляем уведомление пригласившему
                    try:
                        # Формируем текст сообщения
                        new_user_info = f"@{from_user.username}" if from_user.username else f"пользователь (ID: {from_user.id})"
                        ref_message = (
                            "🎉 *Новый реферал!*\n"
                            f"По вашей ссылке зарегистрировался: {new_user_info}\n"
                            f"Ваш бонусный баланс: *{referrer.bonus_balance}*"
                        )
                        
                        # Отправляем сообщение
                        await message.bot.send_message(
                            chat_id=referrer.telegram_id,
                            text=ref_message,
                            parse_mode="Markdown"
                        )
                        logger.debug(f"Notification sent to referrer {referrer.telegram_id}")
                        
                    except Exception as e:
                        logger.error(f"Failed to send notification to referrer: {e}")
                        
                except Exception as e:
                    logger.error(f"Referral processing error: {e}")
                    await session.rollback()
                    await session.commit()  # Коммитим пользователя без реферала
        else:
            logger.debug(f"User already exists: {db_user.id}")
            is_new_user = db_user.is_new
            if is_new_user:
                db_user.is_new = False
                await session.commit()

        # Получаем текст приветствия
        text = get_start_text(is_new_user)
        
        await message.answer(text, reply_markup=main_menu())
        await state.set_state(MainMenu.choosing)

    except Exception as e:
        logger.error(f"Error in cmd_start: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при обработке команды")
        await state.set_state(MainMenu.choosing)
    finally:
        await session.close()


@router.callback_query(lambda c: c.data == "back_main")
async def back_to_main_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        BACK_TO_MENU_TEXT, 
        reply_markup=main_menu()
    )
    await state.set_state(MainMenu.choosing)