from tracemalloc import start

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    FSInputFile,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BusinessConnection,
    CopyTextButton
)
from sqlalchemy import select

from config import BOT_TOKEN
from db.models import UserBot, UserSession
from db.session import AsyncSessionLocal
from core import tasks, user_bot_service

router = Router()

_session_manager = None
_tracker_service = None
_savemod_service = None  # Telethon SaveModService (full-режим)

# MAIN_BOT_ID = int(BOT_TOKEN.split(":")[0])

# router.message.filter(F.bot.id == MAIN_BOT_ID)

def setup_start_handlers(shared_session_manager, tracker_service, savemod_service, user_bot_service):
    global _session_manager, _tracker_service, _savemod_service, _user_bot_service
    _session_manager = shared_session_manager
    _tracker_service = tracker_service
    _savemod_service = savemod_service
    _user_bot_service = user_bot_service


# ─────────────────────── КЛАВИАТУРЫ ─────────────────────────── #

def get_welcome_keyboard(user_id: int, username: str = None) -> InlineKeyboardMarkup:
    profile_url = f"https://t.me/{username}" if username else f"tg://openmessage?user_id={user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Скопировать @username", copy_text=CopyTextButton(text="@TrackerZaki_Bot"))],
        [InlineKeyboardButton(text="⚙ Профиль", url="tg://settings/")],
        [InlineKeyboardButton(text="📕 Инструкция", url="https://teletype.in/@zakiiq/yJ1Gx4dEEV5")],
        [InlineKeyboardButton(text="Подключиться через FullConnection", callback_data="agree")],
        [InlineKeyboardButton(text="Создать своего бота", callback_data="create_bot")],
    ])


def get_profile_keyboard(user: UserSession) -> InlineKeyboardMarkup:
    buttons = []

    sm_text = "🔴 Выключить SaveMod" if user.savemod_enabled else "🟢 Включить SaveMod"
    buttons.append(
        [InlineKeyboardButton(text=sm_text, callback_data="toggle_savemod")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить бота", callback_data="create_bot")])

    # Кнопка трекера только для full-режима и только если запущен
    if getattr(user, 'connection_type', 'full') == "full" and tasks.is_tracker_running(user.bot_user_id):
        buttons.append([InlineKeyboardButton(text="⏹️ Остановить Трекер", callback_data="stop_tracker")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─────────────────────── ПРОФИЛЬ ─────────────────────────── #

# Обновленная функция формирования текста
def _build_profile_text(user_id: int, user: UserSession, user_bots: list) -> str:
    sm_status = "🟢 Включен" if user.savemod_enabled else "🔴 Выключен"
    
    # Формируем список ботов
    bots_list_text = "\n".join([f"• @{b.username}" for b in user_bots]) if user_bots else "<i>нет созданных ботов</i>"
    
    if getattr(user, 'connection_type', 'full') == "business":
        bc_status = "✅ Активно" if user.business_connection_id else "❌ Неактивно"
        profile_header = (
            "👤 <b>Твой профиль:</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"💼 Режим: <b>Business Connection</b>\n"
            f"🔗 Подключение: {bc_status}\n"
            f"💾 SaveMod: {sm_status}\n\n"
        )
    else:
        tr_status = "🟢 Запущен" if tasks.is_tracker_running(user_id) else "🔴 Остановлен"
        profile_header = (
            "👤 <b>Твой профиль:</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"🔐 Режим: <b>Полный доступ</b>\n"
            f"💾 SaveMod: {sm_status}\n"
            f"📡 Tracker: {tr_status}\n\n"
        )

    return (
        profile_header +
        f"🤖 <b>Ваши боты ({len(user_bots)}):</b>\n"
        f"{bots_list_text}\n\n"
        "<b>@TrackerZaki_Bot</b>"
    )

async def safe_edit(message: Message, text: str, reply_markup=None):
    """Редактирует сообщение, игнорируя 'message is not modified'."""
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            print(f"[start] safe_edit error: {e}")


# ─────────────────────── /start ─────────────────────────── #


@router.message(Command("start"))
async def start_command_handler(message: Message):

    user_id = message.from_user.id
    username = message.from_user.username

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        result_bot = await session.execute(
            select(UserBot).where(UserBot.owner_id == user_id)
        )
        my_bots = result_bot.scalars().all()


    # Уже настроен — показываем профиль
    if user and (user.business_connection_id or user.session_string):
        await message.answer(
            _build_profile_text(user_id, user, my_bots),
            reply_markup=get_profile_keyboard(user),
            parse_mode="HTML",
        )
        return
    photo = FSInputFile("Png/starttutor.png")   # ← путь к файлу
    # Новый пользователь — выбор режима
    # Отправляем приветственное фото + текст
    await message.answer_photo(
        photo=photo,
        caption=(
            "👋 <b>Привет!</b>\n\n"
            "Этот бот создан, чтобы дать тебе полный контроль над перепиской в Telegram.\n\n"
            "• Я присылаю уведомления, когда собеседник <b>удаляет или редактирует сообщения</b>.\n"
            "• При полном подключении я также <b>сохраняю самоуничтожающиеся фото, видео и голосовые сообщения</b>.\n\n"
            "Что бы подключить бота, нажмите на кнопку <b>«Скопировать @username»</b> и следуйте инструкции ниже."
        ),
        reply_markup=get_welcome_keyboard(user_id=user_id, username=username),
        parse_mode="HTML",
    )

# ─────────────────────── ВЫБОР РЕЖИМА ─────────────────────── #

@router.callback_query(F.data == "mode_business")
async def callback_mode_business(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = UserSession(
                bot_user_id=user_id,
                savemod_enabled=True,
                connection_type="business",
            )
            session.add(user)
        else:
            user.connection_type = "business"
        await session.commit()

    await safe_edit(
        callback.message,
        "💼 <b>Business Connection</b>\n\n"
        "Чтобы активировать SaveMod:\n\n"
        "1. Открой <b>Настройки Telegram</b>\n"
        "2. Перейди в <b>Telegram для бизнеса → Чат-боты</b>\n"
        "3. Добавь <b>@TrackerZaki_Bot</b>\n\n"
        "После подключения бот автоматически начнёт работать.\n\n"
        "⚠️ Требуется <b>Telegram Premium</b>",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📖 Инструкция", url="https://teletype.in/@zakiiq/7Kq-TRuW_8a")],
            [InlineKeyboardButton(text="🔄 Проверить подключение", callback_data="check_bc")],
        ]),
    )


@router.callback_query(F.data == "check_bc")
async def callback_check_bc(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()

    if user and user.business_connection_id:
        await safe_edit(
            callback.message,
            "✅ <b>Business Connection активен!</b>\n\n"
            "SaveMod работает — удалённые сообщения из бизнес-чатов "
            "будут восстанавливаться и отправляться тебе.\n\n"
            "Напиши /start чтобы открыть профиль.",
        )
    else:
        await safe_edit(
            callback.message,
            "❌ <b>Подключение не найдено</b>\n\n"
            "Убедись что добавил бота в:\n"
            "<b>Настройки → Telegram для бизнеса → Чат-боты</b>\n\n"
            "После добавления нажми кнопку снова.",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Проверить снова", callback_data="check_bc")],
            ]),
        )


# ─────────────────── BUSINESS CONNECTION EVENT ──────────────────── #

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


# ─────────────────── ДИСКЛЕЙМЕР / AGREE ──────────────────── #

@router.callback_query(F.data == "disclamer")
async def callback_disclamer(callback: CallbackQuery):
    await callback.answer()
    await safe_edit(
        callback.message,
        "⚠️ <b>Дисклеймер</b>\n\n"
        "Бота сделал Я, Данечек. Мне все равно на вас, на ваш акк, "
        "если хотите юзайте, если нет — не юзайте. "
        "Я не храню ваши данные, не взламываю аккаунты. "
        "Если есть баги, предложения — пишите мне.",
    )


# ─────────────────── ПРОФИЛЬ CALLBACKS ──────────────────── #

@router.callback_query(F.data == "toggle_savemod")
async def callback_toggle_savemod(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        conn_type = getattr(user, 'connection_type', 'full')

        if conn_type == "full" and _savemod_service:
            # Full-режим: SaveModService управляет Telethon-хендлерами
            if user.savemod_enabled:
                await _savemod_service.disable(user_id)
            else:
                await _savemod_service.enable(user_id)
            # После enable/disable перечитываем актуальный статус из БД
            await session.refresh(user)
        else:
            # Business-режим: просто флаг
            user.savemod_enabled = not user.savemod_enabled
            await session.commit()

    # Перечитываем юзера для актуального текста профиля
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()

    if user:
        await safe_edit(
            callback.message,
            _build_profile_text(user_id, user),
            get_profile_keyboard(user),
        )


@router.callback_query(F.data == "stop_tracker")
async def callback_stop_tracker(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        await _tracker_service.stop(user_id)
        await callback.answer("Трекер остановлен")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSession).where(UserSession.bot_user_id == user_id)
            )
            user = result.scalar_one_or_none()

        if user:
            await safe_edit(
                callback.message,
                _build_profile_text(user_id, user),
                get_profile_keyboard(user),
            )
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)