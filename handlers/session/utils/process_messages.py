from aiogram import types, Bot
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from services.session_manager import SessionManager
from services.timer_manager import TimerManager
from core.persones.persona_decision_layer import PersonaDecisionLayer
from core.persones.persona_humanization_layer import PersonaHumanizationLayer
from core.persones.persona_instruction_layer import PersonaSalterLayer
from core.persones.persona_response_layer import PersonaResponseLayer
from database.crud import get_user
from config import logger
from typing import List
from collections import deque
import asyncio
from datetime import datetime
from typing import List
from .calculate_typing_delay import calculate_typing_delay
from .cleanup import end_session_cleanup
from .lock import session_lock
from .constants import INACTIVITY_DELAY
from typing import List

async def process_messages_after_delay(
    state: FSMContext,
    message: types.Message,
    session: AsyncSession,
    session_manager: SessionManager,
    delay: int,
    bot: Bot,
    timer_manager: TimerManager
):
    """Обрабатывает все сообщения после задержки PROCESSING_DELAY секунд"""
    data = await state.get_data()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    logger.debug(f"[PROCESS MESSAGES] Processing messages after delay {delay}s | session_id={session_id} | user_id={user_id}")
    
    try:
        async with session_lock(state):
            if not await session_manager.is_session_active(user_id, session):
                logger.debug(f"[PROCESS MESSAGES] Session ended before inactivity check | session_id={session_id} | user_id={user_id}")
                return
            
            # Устанавливаем флаг ответа бота
            await state.update_data(is_bot_responding=True)
                
            data = await state.get_data()
            message_queue = deque(data.get("message_queue", []))
            
            if not message_queue:
                logger.debug(f"[PROCESS MESSAGES] No messages in queue to process | session_id={session_id} | user_id={user_id}")
                await state.update_data(is_bot_responding=False)
                return
            
            # Берем ВСЕ сообщения из очереди и объединяем их
            combined_messages = []
            while message_queue:
                combined_messages.append(message_queue.popleft())
            
            combined_message = "\n".join(combined_messages)
            message_queue.clear()
            await state.update_data(message_queue=[])
        
            # Получаем необходимые данные из состояния
            meta_history: List = data.get("meta_history", [])
            decisioner = PersonaDecisionLayer.from_dict(data['decisioner'])
            responser = PersonaResponseLayer.from_dict(data['responser'])
            salter = PersonaSalterLayer.from_dict(data['salter'])
            humanizator = PersonaHumanizationLayer.from_dict(data['humanizator'])
            total_tokens = data.get("total_tokens")
            
            # Логируем пользовательские сообщения
            db_user = await get_user(session, telegram_id=message.from_user.id)
            if db_user:
                logger.debug(f"[PROCESS MESSAGES] Adding user message to history | session_id={session_id} | user_id={user_id}")
                await session_manager.add_message_to_history(
                    db_user.id,
                    combined_message,
                    is_user=True,
                    tokens_used=0
                )
            
            meta_history.append({"role": "Психотерапевт (ваш собеседник)", "content": combined_message})
            
            # Обработка сообщения через все слои ИИ
            logger.debug(f"[PROCESS MESSAGES] Making decision for message | session_id={session_id} | user_id={user_id}")
            
            # Принятие решение
            decision, tokens_used = await decisioner.make_decision(combined_message, meta_history)
            total_tokens += tokens_used
            
            recent_decisions = decisioner.get_recent_decisions()
            
            if decision != "silence":
                try:
                    # Подсолка сообщения
                    logger.debug(f"[PROCESS MESSAGES] Salting message | session_id={session_id} | user_id={user_id}")
                    salted_msg, tokens_used = await salter.salt_message(combined_message, decision, recent_decisions, meta_history)
                    total_tokens += tokens_used
                    
                    # Генерация ответа
                    responser.update_history(salted_msg)
                    logger.debug(f"[PROCESS MESSAGES] Generating response | session_id={session_id} | user_id={user_id}")
                    response, tokens_used = await responser.get_response()
                    total_tokens += tokens_used
                    
                    # Хуманизация ответа
                    logger.debug(f"[PROCESS MESSAGES] Humanizing response | session_id={session_id} | user_id={user_id}")
                    refined_response, tokens_used = await humanizator.humanization_respond(raw_response=response, history=meta_history)
                    total_tokens += tokens_used
                    
                    # Удаление мусора
                    # Депрейкейтед 02.08.2025, попробовал попросить ЛЛМ не использовать символы, которые могут вызвать проблемы, а так же Markdown
                    # refined_response = refined_response.replace("`", "").replace("-", "").replace("'", "")
                    
                    logger.debug(f"[PROCESS MESSAGES] Final LLM response (with humanization): {refined_response} | session_id={session_id} | user_id={user_id}")
                    
                    # Разделение ответа на части
                    response_parts = [part.strip() for part in refined_response.split("||") if part.strip()] if "||" in refined_response else [refined_response]
                    
                    # Обновление истории
                    responser.update_history(" ".join(response_parts), False)
                    meta_history.append({"role": "Вы (пациент)", "content": " ".join(response_parts)})
                    
                    # Отправка ответа - используем переданный bot
                    logger.debug(f"[PROCESS MESSAGES] Sending response parts (count={len(response_parts)}) | session_id={session_id} | user_id={user_id}")
                    for part in response_parts:
                        try:
                            # Запускаем индикатор печатает для каждой части
                            typing_task = asyncio.create_task(
                                bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
                            )
                            delay = calculate_typing_delay(part)
                            await asyncio.sleep(delay)
                            # Отправляем сообщение и ждем завершения
                            await bot.send_message(chat_id=message.chat.id, text=part)
                            # Отменяем индикатор печатает
                            typing_task.cancel()
                            try:
                                await typing_task
                            except asyncio.CancelledError:
                                pass
                            
                        except Exception as e:
                            logger.error(f"[PROCESS MESSAGES] Error sending message: {e} | session_id={session_id} | user_id={user_id}")
                            try:
                                typing_task.cancel()
                            except:
                                pass
                        
                    # Проверяем, есть ли новые сообщения в очереди
                    data = await state.get_data()
                    current_queue = deque(data.get("message_queue", []))
                    if current_queue:
                        logger.debug(f"[PROCESS MESSAGES] New messages arrived during response (count={len(current_queue)}), processing them | session_id={session_id} | user_id={user_id}")
                        await process_messages_after_delay(state, message, session, session_manager, 0, bot, timer_manager)
                    else:
                        await state.update_data(is_bot_responding=False)
                    
                    # Логирование ответа
                    if db_user:
                        logger.debug(f"[PROCESS MESSAGES] Adding bot response to history | session_id={session_id} | user_id={user_id}")
                        await session_manager.add_message_to_history(
                            db_user.id,
                            " ".join(response_parts),
                            is_user=False,
                            tokens_used=total_tokens
                        )
                    
                    if decision == "disengage":
                        logger.debug(f"[PROCESS MESSAGES] Persona decided to disengage | session_id={session_id} | user_id={user_id}")
                        await asyncio.sleep(1)
                        await bot.send_message(chat_id=message.chat.id, text="<i>Персонаж решил уйти...</i>")
                        await end_session_cleanup(message, state, session, session_manager, timer_manager)
                finally:
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass
                    logger.debug(f"[PROCESS MESSAGES] Typing indicator stopped | session_id={session_id} | user_id={user_id}")

                    await state.update_data(is_bot_responding=False)
                    
                    # Проверяем, есть ли новые сообщения в очереди
                    data = await state.get_data()
                    if deque(data.get("message_queue", [])):
                        logger.debug(f"[PROCESS MESSAGES] Processing remaining messages in queue | session_id={session_id} | user_id={user_id}")
                        await process_messages_after_delay(state, message, session, session_manager, 0, bot, timer_manager)
            else:
                # Если персона решила помолчать
                logger.debug(f"[PROCESS MESSAGES] Persona chose silence | session_id={session_id} | user_id={user_id}")
                if combined_message == f"*молчание в течение {INACTIVITY_DELAY} секунд...*":
                    await bot.send_message(chat_id=message.chat.id, text="<i>Персонаж молчит в ответ на ваше молчание.</i>")
                else:
                    await bot.send_message(chat_id=message.chat.id, text="<i>Персонаж предпочел не отвечать на это.</i>")
                responser.update_history("*молчание, ваш персонаж (пациент) предпочел не отвечать*", False)
                meta_history.append({"role": "Вы (пациент)", "content": "*молчание, ваш персонаж (пациент) предпочел не отвечать*"})
                if db_user:
                    async with session_lock(state):
                        logger.debug(f"Adding silence to history | session_id={session_id} | user_id={user_id}")
                        await session_manager.add_message_to_history(
                            db_user.id,
                            "Персонаж предпочел не отвечать на это.",
                            is_user=False,
                            tokens_used=total_tokens
                        )
            # Обновляем состояние и перезапускаем таймеры
            async with session_lock(state):
                await state.update_data(
                    is_bot_responding=False,
                    last_activity=datetime.now().isoformat(),
                    meta_history=meta_history,
                    total_tokens=total_tokens
                )
                # Перезапускаем таймер неактивности через менеджер
                logger.debug(f"[PROCESS MESSAGES] Restarting inactivity timer | session_id={session_id} | user_id={user_id}")
                await timer_manager.cancel_timer(session_id, 'inactivity_timer')

    except Exception as e:
        logger.error(f"[PROCESS MESSAGES] Error processing messages: {e} | session_id={session_id} | user_id={user_id}")
        await state.update_data(is_bot_responding=False)
    finally:
        # Проверяем, нужно ли завершить сессию после ответа
        data = await state.get_data()
        if data.get("should_end_session_after_response", False):
            await end_session_cleanup(message, state, session, session_manager, timer_manager)
        session.close()
        
        
async def check_inactivity(
    state: FSMContext,
    message: types.Message,
    delay: int,
    session: AsyncSession,
    session_manager: SessionManager,
    bot: Bot,
    timer_manager: TimerManager
):
    """Проверяет неактивность пользователя с учетом сообщений бота в течении INACTIVITY_DELAY секунд"""
    data = await state.get_data()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    logger.debug(f"[INACTIVITY CHECK] Starting inactivity check (delay={delay}s) | session_id={session_id} | user_id={user_id}")
    
    try:
        async with session_lock(state):
            # Проверяем, активна ли ещё сессия
            if not await session_manager.is_session_active(user_id, session):
                logger.debug(f"[INACTIVITY CHECK] Session ended before inactivity check | session_id={session_id} | user_id={user_id}")
                return
                
            data = await state.get_data()
            # Если бот отвечает, откладываем проверку неактивности
            if data.get('is_bot_responding', False):
                logger.debug(f"[INACTIVITY CHECK] Bot is responding - postponing inactivity check | session_id={session_id} | user_id={user_id}")
                return
            
            last_activity = data.get('last_activity', datetime.min)
            inactive_seconds = (datetime.now() - last_activity).total_seconds()
            
            logger.debug(f"[INACTIVITY CHECK] Current inactivity: {inactive_seconds:.1f}s | session_id={session_id} | user_id={user_id}")
            
            if inactive_seconds < delay:
                logger.debug(f"[INACTIVITY CHECK] Activity detected, cancelling inactivity check | session_id={session_id} | user_id={user_id}")
                return  # Была активность
                
            message_queue = deque(data.get("message_queue", []))
            
            if not message_queue:
                logger.debug(f"[INACTIVITY CHECK] No messages in queue, adding silence message | session_id={session_id} | user_id={user_id}")
                
                # Добавляем специальное сообщение о молчании в очередь
                silence_message = f"*молчание в течение {INACTIVITY_DELAY} секунд...*"
                
                # Обновляем состояние с новой очередью и флагом ответа бота
                await state.update_data(
                    message_queue=[silence_message],
                    is_bot_responding=True,
                    last_activity=datetime.now().isofromat()  # Обновляем активность
                )
                
                 # Логируем пользовательские сообщения
                db_user = await get_user(session, telegram_id=message.from_user.id)
                if db_user:
                    logger.debug(f"[INACTIVITY CHECK] Adding user message to history | session_id={session_id} | user_id={user_id}")
                    await session_manager.add_message_to_history(
                        db_user.id,
                        silence_message,
                        is_user=True,
                        tokens_used=0 # Логгированием сообщение пользователя о молчании
                    )
                
                # Запускаем обработку сообщения о молчании
                await process_messages_after_delay(
                    state, 
                    message, 
                    session, 
                    session_manager, 
                    0,  # Немедленная обработка
                    bot, 
                    timer_manager              
                )  
                
    except asyncio.CancelledError:
        logger.debug(f"[INACTIVITY CHECK] Inactivity check cancelled | session_id={session_id} | user_id={user_id}")
    except Exception as e:
        logger.error(f"[INACTIVITY CHECK] Inactivity check error: {e} | session_id={session_id} | user_id={user_id}")
        
    finally:
        session.close()