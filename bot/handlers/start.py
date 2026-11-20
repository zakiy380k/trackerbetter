from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    FSInputFile,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BusinessConnection,
    CopyTextButton,
)
from sqlalchemy import select

from db.models import UserBot, UserSession
from db.session import AsyncSessionLocal
from core import tasks

router = Router()

_session_manager = None
_tracker_service = None
_savemod_service = None
_user_bot_service = None

BOT_USERNAME_TAG = "@TrackerZaki_Bot"

WELCOME_TEXT = (
    "👋 <b>Привет!</b>\n\n"
    "Этот бот создан, чтобы дать тебе полный контроль над перепиской в Telegram.\n\n"
    "• Я присылаю уведомления, когда собеседник <b>удаляет или редактирует сообщения</b>.\n"
    "• <b>Присылаю медиа с огоньком</b>.\n\n"
    "Нажми <b>«Подключить»</b>, чтобы выбрать способ подключения."
)

CONNECT_TEXT = (
    "🔌 <b>Выбери способ подключения</b>\n\n"
    "• <b>Business Connection</b> — быстро, безопасно.\n"
    "• <b>Full Connection</b> — через сессии. Дает возможность мониторинг активности человека."
)

BUSINESS_TEXT = (
    "💼 <b>Business Connection</b>\n\n"
    "Короткая инструкция:\n"
    "1. Нажми <b>«Скопировать @username»</b> ниже.\n"
    "2. Открой <b>Настройки Telegram → Мой аккаунт → Изменить → Автоматизация чатов</b>.\n"
    "3. Вставь <b>@TrackerZaki_Bot</b> и сохрани.\n\n"

)


def setup_start_handlers(shared_session_manager, tracker_service, savemod_service, user_bot_service):
    global _session_manager, _tracker_service, _savemod_service, _user_bot_service
    _session_manager = shared_session_manager
    _tracker_service = tracker_service
    _savemod_service = savemod_service
    _user_bot_service = user_bot_service


# ─────────────────────── КЛАВИАТУРЫ ─────────────────────────── #

def get_welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔌 Подключить", callback_data="open_connect")],
        [InlineKeyboardButton(text="📕 Инструкция", url="https://teletype.in/@zakiiq/yJ1Gx4dEEV5")],
        [InlineKeyboardButton(text="🤖 Создать своего бота", callback_data="create_bot")],
    ])


def get_connect_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Full Connection", callback_data="agree")],
        [InlineKeyboardButton(text="💼 Business Connection", callback_data="mode_business")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_welcome")],
    ])


def get_business_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Скопировать @username", copy_text=CopyTextButton(text=BOT_USERNAME_TAG))],
        [InlineKeyboardButton(text="⚙ Профиль", url="tg://settings/")],
        [InlineKeyboardButton(text="🔄 Проверить подключение", callback_data="check_bc")],
        [InlineKeyboardButton(text="← Назад", callback_data="open_connect")],
    ])


def get_profile_keyboard(user: UserSession) -> InlineKeyboardMarkup:
    buttons = []

    sm_text = "🔴 Выключить SaveMod" if user.savemod_enabled else "🟢 Включить SaveMod"
    buttons.append([InlineKeyboardButton(text=sm_text, callback_data="toggle_savemod")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить бота", callback_data="create_bot")])

    if getattr(user, "connection_type", "full") == "full" and tasks.is_tracker_running(user.bot_user_id):
        buttons.append([InlineKeyboardButton(text="⏹️ Остановить Трекер", callback_data="stop_tracker")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─────────────────────── ПРОФИЛЬ ─────────────────────────── #

def _build_profile_text(user_id: int, user: UserSession, user_bots: list) -> str:
    sm_status = "🟢 Включен" if user.savemod_enabled else "🔴 Выключен"
    bots_list_text = "\n".join([f"• @{b.username}" for b in user_bots]) if user_bots else "<i>нет созданных ботов</i>"

    if getattr(user, "connection_type", "full") == "business":
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
        profile_header
        + f"🤖 <b>Ваши боты ({len(user_bots)}):</b>\n"
        + f"{bots_list_text}\n\n"
        + "<b>@TrackerZaki_Bot</b>"
    )


async def safe_edit(message: Message, text: str, reply_markup=None):
    """Редактирует текст или подпись к фото, игнорируя 'message is not modified'."""
    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            print(f"[start] safe_edit error: {e}")


# ─────────────────────── /start ─────────────────────────── #

@router.message(Command("start"))
async def start_command_handler(message: Message):
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()

        result_bot = await session.execute(
            select(UserBot).where(UserBot.owner_id == user_id)
        )
        my_bots = result_bot.scalars().all()

    if user and (user.business_connection_id or user.session_string):
        await message.answer(
            _build_profile_text(user_id, user, my_bots),
            reply_markup=get_profile_keyboard(user),
            parse_mode="HTML",
        )
        return

    photo = FSInputFile("Png/starttutor.png")
    await message.answer_photo(
        photo=photo,
        caption=WELCOME_TEXT,
        reply_markup=get_welcome_keyboard(),
        parse_mode="HTML",
    )


# ─────────────────────── НАВИГАЦИЯ ПОДКЛЮЧЕНИЯ ─────────────────────── #

@router.callback_query(F.data == "back_welcome")
async def callback_back_welcome(callback: CallbackQuery):
    await callback.answer()
    await safe_edit(
        callback.message,
        WELCOME_TEXT,
        get_welcome_keyboard(),
    )


@router.callback_query(F.data == "open_connect")
async def callback_open_connect(callback: CallbackQuery):
    await callback.answer()
    await safe_edit(
        callback.message,
        CONNECT_TEXT,
        get_connect_keyboard(),
    )


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
        BUSINESS_TEXT,
        get_business_keyboard(),
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
            get_business_keyboard(),
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


# ─────────────────── ДИСКЛЕЙМЕР ──────────────────── #

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

        conn_type = getattr(user, "connection_type", "full")

        if conn_type == "full" and _savemod_service:
            if user.savemod_enabled:
                await _savemod_service.disable(user_id)
            else:
                await _savemod_service.enable(user_id)
            await session.refresh(user)
        else:
            user.savemod_enabled = not user.savemod_enabled
            await session.commit()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserSession).where(UserSession.bot_user_id == user_id)
        )
        user = result.scalar_one_or_none()

        result_bot = await session.execute(
            select(UserBot).where(UserBot.owner_id == user_id)
        )
        my_bots = result_bot.scalars().all()

    if user:
        await safe_edit(
            callback.message,
            _build_profile_text(user_id, user, my_bots),
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

            result_bot = await session.execute(
                select(UserBot).where(UserBot.owner_id == user_id)
            )
            my_bots = result_bot.scalars().all()

        if user:
            await safe_edit(
                callback.message,
                _build_profile_text(user_id, user, my_bots),
                get_profile_keyboard(user),
            )
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
