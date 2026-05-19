# bot/handlers/user_bot_handlers.py

from sqlalchemy import select

import logging
from core.tasks import is_tracker_running
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import (
    FSInputFile,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BusinessConnection,
    CopyTextButton,
    BusinessMessagesDeleted
)


from aiogram.fsm.context import FSMContext
from db.session import AsyncSessionLocal


from core.user_bot_service import UserBotService
from bot.handlers.tracker import CreateBotStates
from db.models import UserSession  # если нужно

router = Router(name="user_bot_main")

# MAIN_BOT_ID = int(BOT_TOKEN.split(":")[0])


# router.message.filter(F.bot.id != MAIN_BOT_ID)

_savemod_service = None
_session_manager = None

def setup_user_bot_handlers(savemod_service, session_manager):
    global _savemod_service, _session_manager
    _savemod_service = savemod_service
    _session_manager = session_manager



# ─────────────────────── КЛАВИАТУРЫ ─────────────────────────── #

def get_welcome_keyboard(user_id: int, username: str = None) -> InlineKeyboardMarkup:
    profile_url = f"https://t.me/{username}" if username else f"tg://openmessage?user_id={user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Скопировать @username", copy_text=CopyTextButton(text="@TrackerZaki_Bot"))],
        [InlineKeyboardButton(text="⚙ Профиль", url="tg://settings/")],
        [InlineKeyboardButton(text="📕 Инструкция", url="https://teletype.in/@zakiiq/yJ1Gx4dEEV5")],
        [InlineKeyboardButton(text="Подключиться через FullConnection", callback_data="agree")],
        [InlineKeyboardButton(text="Создать своего боат", callback_data="create_bot")],
    ])

def get_profile_keyboard(user: UserSession) -> InlineKeyboardMarkup:
    buttons = []

    sm_text = "🔴 Выключить SaveMod" if user.savemod_enabled else "🟢 Включить SaveMod"
    buttons.append([InlineKeyboardButton(text=sm_text, callback_data="toggle_savemod")])

    # Кнопка трекера только для full-режима и только если запущен
    if getattr(user, 'connection_type', 'full') == "full" and is_tracker_running(user.bot_user_id):
        buttons.append([InlineKeyboardButton(text="⏹️ Остановить Трекер", callback_data="stop_tracker")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)



# ─────────────────────── ПРОФИЛЬ ─────────────────────────── #

def _build_profile_text(
    user_id: int,
    user: UserSession,
    bot_username: str
) -> str:
    sm_status = "🟢 Включен" if user.savemod_enabled else "🔴 Выключен"

    if getattr(user, 'connection_type', 'full') == "business":
        bc_status = "✅ Активно" if user.business_connection_id else "❌ Неактивно"
        return (
            "👤 <b>Твой профиль:</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"💼 Режим: <b>Business Connection</b>\n"
            f"🔗 Подключение: {bc_status}\n"
            f"💾 SaveMod: {sm_status}\n\n"
            f"<b>@{bot_username}</b>"        )
    else:
        tr_status = "🟢 Запущен" if is_tracker_running(user_id) else "🔴 Остановлен"
        return (
            "👤 <b>Твой профиль:</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"🔐 Режим: <b>Полный доступ</b>\n"
            f"💾 SaveMod: {sm_status}\n"
            f"📡 Tracker: {tr_status}\n\n"
            "<b>@TrackerZaki_Bot</b>"
        )


# ─────────────────────── /start ─────────────────────────── #

# @router.message(F.text == "/start")
# async def start_command_handler(message: Message):
#     if message.bot.token == BOT_TOKEN:
#         return
#     user_id = message.from_user.id
#     username = message.from_user.username

#     async with AsyncSessionLocal() as session:
#         result = await session.execute(
#             select(UserSession).where(UserSession.bot_user_id == user_id)
#         )
#         user = result.scalar_one_or_none()

#     # Уже настроен — показываем профиль
#     if user and (user.business_connection_id or user.session_string):
#         await message.answer(
#             _build_profile_text(user_id, user),
#             reply_markup=get_profile_keyboard(user),
#             parse_mode="HTML",
#         )
#         return
#     photo = FSInputFile("Png/starttutor.png")   # ← путь к файлу
#     # Новый пользователь — выбор режима
#     # Отправляем приветственное фото + текст
#     await message.answer_photo(
#         photo=photo,
#         caption=(
#             "👋 <b>Привет!</b>\n\n"
#             "Этот бот создан, чтобы дать тебе полный контроль над перепиской в Telegram.\n\n"
#             "• Я присылаю уведомления, когда собеседник <b>удаляет или редактирует сообщения</b>.\n"
#             "• При полном подключении я также <b>сохраняю самоуничтожающиеся фото, видео и голосовые сообщения</b>.\n\n"
#             "Что бы подключить бота, нажмите на кнопку <b>«Скопировать @username»</b> и следуйте инструкции ниже."
#         ),
#         reply_markup=get_welcome_keyboard(user_id=user_id, username=username),
#         parse_mode="HTML",
#     )


@router.message(Command("start"))
async def user_bot_start(message: Message):
    # Если это главный бот — передаем управление дальше


    logging.info(f"🎯 Хендлер Юзер-Бота поймал /start от пользователя {message.from_user.id}")

    try:
        # Для теста сначала отправим обычный текст без сложных клавиатур
        await message.answer(
            "👋 <b>Привет! Я твой персональный Юзер-Бот.</b>\n\n"
            "Я успешно запущен и готов к работе.\n\n"
            "Доступные команды:\n"
            "🔹 /savemod_on — включить SaveMod\n"
            "🔹 /savemod_off — выключить SaveMod\n"
            "🔹 /tracker [username] — запустить трекер"
        )
    except Exception as e:
        logging.error(f"❌ Ошибка отправки ответа в кастомном боте: {e}")

async def safe_edit(message: Message, text: str, reply_markup=None):
    """Редактирует сообщение, игнорируя 'message is not modified'."""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            print(f"[start] safe_edit error: {e}")



@router.business_connection()
async def on_business_connection(bc: BusinessConnection):
    """Срабатывает когда юзер подключает/отключает бота как бизнес-бота."""
    from core.business_savemod_service import get_service

    user_id = bc.user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()

        if bc.is_enabled:
            if not user:
                user = UserSession(
                    bot_user_id=user_id,
                    savemod_enabled=True,
                    connection_type="business",
                    business_connection_id=bc.id,
                )
                session.add(user)
            else:
                user.connection_type = "business"
                user.business_connection_id = bc.id
                user.savemod_enabled = True
            await session.commit()

            # register_connection — синхронный метод, await не нужен
            try:
                get_service().register_connection(bc.id, user_id)
            except Exception as e:
                print(f"[BC] register_connection error: {e}")

            try:
                await bc.bot.send_message(
                    user_id,
                    "✅ <b>Business Connection подключён!</b>\n\n"
                    "SaveMod активирован — удалённые сообщения из бизнес-чатов "
                    "будут восстанавливаться и отправляться тебе.\n\n"
                    "Напиши /start для управления.",
                    parse_mode="HTML",
                )
            except Exception as e:
                print(f"[BC] Уведомление не доставлено {user_id}: {e}")
        else:
            # Пользователь отключил бота
            if user:
                user.business_connection_id = None
                await session.commit()
            try:
                await bc.bot.send_message(
                    user_id,
                    "❌ Business Connection отключён. SaveMod деактивирован.",
                )
            except Exception:
                pass



@router.message(Command("help"))
async def user_help(message: Message):
    await message.answer(
        "📋 <b>Доступные команды:</b>\n\n"
        "/start — приветствие\n"
        "/savemod_on — включить SaveMod\n"
        "/savemod_off — выключить SaveMod\n"
        "/tracker [username|id] — запустить трекер\n"
        "/stop — остановить трекер\n"
        "/id — узнать ID",
        parse_mode="HTML"
    )


# Подключаем основные команды из tracker.py
@router.message(Command("savemod_on"))
async def user_savemod_on(message: Message):

    user_id = message.from_user.id
    if not _savemod_service:
        return await message.answer("❌ SaveMod сервис недоступен.")
    try:
        await _savemod_service.enable(user_id)
        await message.answer("✅ SaveMod включён (UserBot)")
    except Exception as e:
        await message.answer(f"❌ Не удалось включить SaveMod: {e}")

@router.message(Command("savemod_off"))
async def user_savemod_off(message: Message):

    user_id = message.from_user.id
    if not _savemod_service:
        return await message.answer("❌ SaveMod сервис недоступен.")
    try:
        await _savemod_service.disable(user_id)
        await message.answer("❌ SaveMod выключен (UserBot)")
    except Exception as e:
        await message.answer(f"❌ Не удалось выключить SaveMod: {e}")


@router.message(Command("tracker"))
async def user_tracker(message: Message, tracker_service):

    await message.answer("🔄 Функция трекера в разработке для UserBot")

@router.message(Command("mark"))
async def user_mark(message: Message):
    await message.answer("Danger") 

@router.message(Command("auth"))
async def user_auth(message: Message):
    pass

@router.edited_business_message()
async def on_custom_bot_edited_business_message(message: Message):
    # Вместо заглушки вызываем сервис бизнес-сейвмода напрямую
    from core.business_savemod_service import get_service
    
    # Это вызовет ту же логику, что и в основном бизнес-боте
    await get_service().handle_edited_message(message)

@router.deleted_business_messages()
async def on_custom_bot_deleted_business_messages(event: BusinessMessagesDeleted):
    from core.business_savemod_service import get_service
    
    # Используем тот же метод, что и в бизнес-сервисе
    await get_service().handle_deleted_messages(event)