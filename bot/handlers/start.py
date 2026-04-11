from aiogram import Router, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BusinessConnection,
)
from sqlalchemy import select

from db.models import UserSession
from db.session import AsyncSessionLocal
from core import tasks

router = Router()

_session_manager = None
_tracker_service = None
_savemod_service = None  # Telethon SaveModService (full-режим)


def setup_start_handlers(shared_session_manager, tracker_service, savemod_service):
    global _session_manager, _tracker_service, _savemod_service
    _session_manager = shared_session_manager
    _tracker_service = tracker_service
    _savemod_service = savemod_service


# ─────────────────────── КЛАВИАТУРЫ ─────────────────────────── #

def get_welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💼 ТГ Премиум (SaveMod)", callback_data="mode_business")],
        [InlineKeyboardButton(text="🔐 Без ТГ Премиум (SaveMod + Tracker)", callback_data="agree")],
        [InlineKeyboardButton(text="📋 Дисклеймер", callback_data="disclamer")],
    ])


def get_profile_keyboard(user: UserSession) -> InlineKeyboardMarkup:
    buttons = []

    sm_text = "🔴 Выключить SaveMod" if user.savemod_enabled else "🟢 Включить SaveMod"
    buttons.append([InlineKeyboardButton(text=sm_text, callback_data="toggle_savemod")])

    # Кнопка трекера только для full-режима и только если запущен
    if getattr(user, 'connection_type', 'full') == "full" and tasks.is_tracker_running(user.bot_user_id):
        buttons.append([InlineKeyboardButton(text="⏹️ Остановить Трекер", callback_data="stop_tracker")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─────────────────────── ПРОФИЛЬ ─────────────────────────── #

def _build_profile_text(user_id: int, user: UserSession) -> str:
    sm_status = "🟢 Включен" if user.savemod_enabled else "🔴 Выключен"

    if getattr(user, 'connection_type', 'full') == "business":
        bc_status = "✅ Активно" if user.business_connection_id else "❌ Неактивно"
        return (
            "👤 <b>Твой профиль:</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"💼 Режим: <b>Business Connection</b>\n"
            f"🔗 Подключение: {bc_status}\n"
            f"💾 SaveMod: {sm_status}\n\n"
            "<b>@TrackerZaki_Bot</b>"
        )
    else:
        tr_status = "🟢 Запущен" if tasks.is_tracker_running(user_id) else "🔴 Остановлен"
        return (
            "👤 <b>Твой профиль:</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"🔐 Режим: <b>Полный доступ</b>\n"
            f"💾 SaveMod: {sm_status}\n"
            f"📡 Tracker: {tr_status}\n\n"
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

@router.message(F.text == "/start")
async def start_command_handler(message: Message):
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()

    # Уже настроен — показываем профиль
    if user and (user.business_connection_id or user.session_string):
        await message.answer(
            _build_profile_text(user_id, user),
            reply_markup=get_profile_keyboard(user),
            parse_mode="HTML",
        )
        return

    # Новый пользователь — выбор режима
    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Выбери режим работы бота:\n\n"
        "💼 <b>Business Connection (ТГ Премиум)</b>\n"
        "Подключаешь бота как бизнес-бота в настройках TG. "
        "SaveMod сохраняет удалённые сообщения из бизнес-чатов.\n\n"
        "🔐 <b>Полный доступ (без Премиума)</b>\n"
        "Регистрируешь аккаунт в боте. "
        "Доступны SaveMod + Трекер активности.\n\n"
        "🔽 Выбери режим:",
        reply_markup=get_welcome_keyboard(),
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