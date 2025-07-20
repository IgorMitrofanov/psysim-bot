from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states import MainMenu
from keyboards.builder import (
    session_resistance_menu,
    session_emotion_menu,
    session_format_menu,
    session_confirm_menu,
    main_menu,
    persona_selection_menu,
    subscription_keyboard_when_sessions_left
)
from datetime import datetime, timedelta
from config import config
from core.persones.persona_behavior import PersonaBehavior
from core.persones.persona_loader import load_personas
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user, save_session
from texts.session_texts import (
    SESSION_RESISTANCE_SELECT,
    EMOTION_SELECT_TEXT,
    FORMAT_SELECT_TEXT,
    CONFIRM_SESSION_TEXT,
    SESSION_STARTED_TEXT,
    NO_USER_TEXT,
    SESSION_RESET_TEXT,
    SESSION_RESET_ERROR_TEXT,
    PERSONA_NO_FOUND_TEXT,
    SESSION_END_TEXT,
    NO_QUOTA_OR_BONUS_FOR_SESSION,
    CHOOSE_PERSONE_FOR_SESSION_TEXT,
    res_map,
    emo_map,
    format_map
)
from texts.common import BACK_TO_MENU_TEXT
from aiogram.types import Message
from services.session_manager import SessionManager
from aiogram.filters import Command

router = Router(name="session")

# ВАЖНО: Здесь используется абстрактный менеджер работы с сессиями, он работает с user_id [int] - это айди из БД, не телеграм айди!
# Менеджер сам найдет телеграм айди юзера с помощью метода из crud

# --- Команда ресета - вынужденной остановки сессии, она в БД не записывается ---
@router.message(Command("reset_session"))
async def reset_session_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    data = await state.get_data()
    session_id = data.get("session_id")

    if session_id:
        await session_manager.abort_session(message.from_user.id, session, session_id=session_id)
        await message.answer(SESSION_RESET_TEXT)
    else:
        await message.answer(SESSION_RESET_ERROR_TEXT)

    await state.clear()
    await message.answer(BACK_TO_MENU_TEXT, reply_markup=main_menu())
    await state.set_state(MainMenu.choosing)


# --- Обработка сообщений во время сессии ---
@router.message(MainMenu.in_session)
async def session_interaction_handler(
    message: types.Message, 
    state: FSMContext,
    session: AsyncSession,
    session_manager: SessionManager
):
    data = await state.get_data()
    persona: PersonaBehavior = data.get("persona")
    if not persona:
        await message.answer(PERSONA_NO_FOUND_TEXT)
        return
    db_user = await get_user(session, telegram_id=message.from_user.id)
    # Проверяем, активна ли еще сессия
    if not await session_manager.is_session_active(db_user.id, session):
        # Сессия закончилась, сообщаем юзеру и возвращаемся в главное меню
        await message.answer(SESSION_END_TEXT)
        await message.answer(BACK_TO_MENU_TEXT, reply_markup=main_menu())
        await state.clear()
        await state.set_state(MainMenu.choosing)
        return
    # Сессия еще активна
    # Добавляем сообщение пользователя в историю
    await session_manager.add_message_to_history(
        db_user.id,
        message.text,
        is_user=True,
        tokens_used=len(message.text) // 4 # Приблизительная оценка 4 сивола ~ 1 токен
    )

    # Обработка сообщения от абстрактной "персоны"
    # TODO: модернизировать - надо чтобы персона брала сообщения пользователя из очереди сообщений за каждый определенный случаный интервал и отвечала сразу на эту пачку
    response, tokens_used = await persona.send(message.text)
    await message.answer(response)
    
    # Добавляем ответ "персоны" в историю
    await session_manager.add_message_to_history(
        db_user.id,
        response,
        is_user=False,
        tokens_used=tokens_used
    )

# --- Старт сессии ---
@router.callback_query(lambda c: c.data == "main_start_session")
async def main_start_session_handler(
    callback: types.CallbackQuery, 
    state: FSMContext, 
    session: AsyncSession,
    session_manager
):
    db_user = await get_user(session, telegram_id=callback.from_user.id)
    if not db_user:
        await callback.message.edit_text(NO_USER_TEXT)
        return

    await callback.message.edit_text(
        SESSION_RESISTANCE_SELECT,
        reply_markup=session_resistance_menu()
    )
    await state.set_state(MainMenu.session_resistance)

# --- Подтверждение сессии ---
@router.callback_query(MainMenu.session_confirm)
async def session_confirm_handler(
    callback: types.CallbackQuery, 
    state: FSMContext, 
    session: AsyncSession,
    session_manager
):
    await callback.answer()
    match callback.data:
        # Меню подтверждения: начать сессию, назад
        case "session_confirm_start":
            # Подготовка к началу сессии
            data = await state.get_data()
            persona_name = data.get("persona_name")
            personas = load_personas()
            persona_data = personas.get(persona_name)
            if not persona_data:
                await callback.message.edit_text("Персонаж не найден. Попробуйте снова.")
                await state.set_state(MainMenu.session_format)
                return
            # Создаем "персону"
            persona = PersonaBehavior(persona_data)
            
            resistance_raw = data.get("resistance")
            emotion_raw = data.get("emotion")
            format_raw = data.get("format")
            
            res_lvl =res_map.get(resistance_raw)
            emo_lvl = emo_map.get(emotion_raw)
            format = format_map.get(format_raw)
            # Задаем ей состояние
            persona.reset(
                resistance_level=res_lvl,
                emotional_state=emo_lvl,
                format=format
            )
            # Получаем юзера из БД
            db_user = await get_user(session, telegram_id=callback.from_user.id)
            if not db_user:
                # Обработка ошибки если он не найден
                await callback.message.edit_text(NO_USER_TEXT)
                return

            # Пытаемся списать квоту или бонус
            used, is_free = await session_manager.use_session_quota_or_bonus(session, db_user.id)
            if not used:
                # Предлагаем купить, если нет ресурсов на сессию
                await callback.message.answer(
                    NO_QUOTA_OR_BONUS_FOR_SESSION,
                    reply_markup=subscription_keyboard_when_sessions_left()
                )
                return
            
            # Делегируем менеджеру сессий начать сессию, и запрашиваем у него ее айди
            session_id = await session_manager.start_session(
                db_session=session,
                user_id=db_user.id,
                is_free=is_free,
                persona_name=persona_name,
                resistance=res_lvl,
                emotion=emo_lvl
            )
            # Обновляем данные в стейт
            await state.update_data(
                persona=persona,
                session_start=datetime.utcnow().isoformat(),
                session_id=session_id,
                resistance=res_lvl,
                emotion=emo_lvl,
                format=format
            )
            # Сообщение о начале сессии
            await callback.message.edit_text(
                SESSION_STARTED_TEXT.format(
                    resistance=res_lvl,
                    emotion=emo_lvl,
                    selected_persona=persona.name,
                    format=format
                )
            )
            # Стейт - в сессии
            await state.set_state(MainMenu.in_session)

        case "back_main":
            # Идем назад
            await callback.message.edit_text(
                BACK_TO_MENU_TEXT,
                reply_markup=main_menu()
            )
            await state.set_state(MainMenu.choosing)


# --- Выбор сопротивления ---
@router.callback_query(MainMenu.session_resistance)
async def session_resistance_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["resistance_medium", "resistance_high"]:
        # Выбор
        await state.update_data(resistance=callback.data)
        await callback.message.edit_text(
            EMOTION_SELECT_TEXT,
            reply_markup=session_emotion_menu()
        )
        await state.set_state(MainMenu.session_emotion)
    elif callback.data == "back_main":
        # Назад
        await callback.message.edit_text(
            BACK_TO_MENU_TEXT,
            reply_markup=main_menu()
        )
        await state.set_state(MainMenu.choosing)


# --- Выбор эмоции ---
@router.callback_query(MainMenu.session_emotion)
async def session_emotion_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data.startswith("emotion_"):
        # Выбор
        await state.update_data(emotion=callback.data)
        await callback.message.edit_text(
            FORMAT_SELECT_TEXT,
            reply_markup=session_format_menu()
        )
        await state.set_state(MainMenu.session_format)
    elif callback.data == "back_to_resistance":
        # Вернутся к выбору сопротивления
        await callback.message.edit_text(
            SESSION_RESISTANCE_SELECT,
            reply_markup=session_resistance_menu()
        )
        await state.set_state(MainMenu.session_resistance)

# --- Выбор формата --- 
# На самом деле думаю убрать это. Просто если риходит голосовая от пользователя - если тариф 
# позволяет - обрабатываем, если нет, предалагем перейти на тариф где есть гс
@router.callback_query(MainMenu.session_format)
async def session_format_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data in ["format_text", "format_audio"]:
        await state.update_data(format=callback.data)

        personas = load_personas()
        persona_names = list(personas.keys())

        await callback.message.edit_text(
            CHOOSE_PERSONE_FOR_SESSION_TEXT,
            reply_markup=persona_selection_menu(persona_names)
        )
        await state.set_state(MainMenu.session_persona)

    elif callback.data == "back_to_emotion":
        await callback.message.edit_text(
            EMOTION_SELECT_TEXT,
            reply_markup=session_emotion_menu()
        )
        await state.set_state(MainMenu.session_emotion)


# --- Выбор персонажа ---
@router.callback_query(MainMenu.session_persona)
async def session_persona_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    if callback.data.startswith("persona_"):
        selected_persona = callback.data.replace("persona_", "")
        await state.update_data(persona_name=selected_persona)

        await callback.message.edit_text(
            CONFIRM_SESSION_TEXT + f"\n\n🧍 Персонаж: {selected_persona}",
            reply_markup=session_confirm_menu()
        )
        await state.set_state(MainMenu.session_confirm)

    elif callback.data == "back_to_format":
        await callback.message.edit_text(
            FORMAT_SELECT_TEXT,
            reply_markup=session_format_menu()
        )
        await state.set_state(MainMenu.session_format)