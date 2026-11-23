from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    FSInputFile,
    Message,
    CallbackQuery,
    BusinessConnection,
)
from aiogram.methods.base import TelegramMethod
from sqlalchemy import select

from db.models import UserBot, UserSession
from db.session import AsyncSessionLocal
from core import tasks

router = Router()


class SendRichMessage(TelegramMethod[Message]):
    """sendRichMessage для Telegram Bot API 10.1+."""
    __returning__ = Message
    __api_method__ = "sendRichMessage"

    chat_id: int
    rich_message: dict


class EditRichMessageText(TelegramMethod[Message]):
    """editMessageText с параметром rich_message."""
    __returning__ = Message
    __api_method__ = "editMessageText"

    chat_id: int
    message_id: int
    rich_message: dict


async def send_rich_message(bot, chat_id: int, html: str, media=None):
    rich_message = {"html": html}
    if media is not None:
        rich_message["media"] = [{
            "id": "start_cover",
            "media": {"type": "photo", "media": media},
        }]
    return await bot(SendRichMessage(chat_id=chat_id, rich_message=rich_message))


def _rich_button(text: str, *, callback_data=None, url=None,
                 copy_text=None, style=None) -> str:
    import html as html_lib

    attrs = []
    if style:
        attrs.append(f'style="{html_lib.escape(style, quote=True)}"')

    if callback_data is not None:
        attrs.extend([
            'type="callback_data"',
            f'data="{html_lib.escape(callback_data, quote=True)}"',
        ])
    elif url is not None:
        attrs.extend([
            'type="url"',
            f'url="{html_lib.escape(url, quote=True)}"',
        ])
    elif copy_text is not None:
        attrs.extend([
            'type="copy_text"',
            f'text="{html_lib.escape(copy_text, quote=True)}"',
        ])
    else:
        raise ValueError("Для Rich-кнопки нужно указать callback_data, url или copy_text")

    return f"<tg-button {' '.join(attrs)}>{html_lib.escape(text)}</tg-button>"


def _button_row(*buttons: str) -> str:
    return "<tg-button-row>" + "".join(buttons) + "</tg-button-row>"




_session_manager = None
_tracker_service = None
_savemod_service = None
_user_bot_service = None

BOT_USERNAME_TAG = "@TrackerZaki_Bot"

# Подставь сюда реальные custom_emoji_id из своего эмодзи-пака
EMOJI_GUIDE = "5312536423851630001"
EMOJI_CREATE_BOT = "5312536423851630002"
EMOJI_CONNECT = "5312536423851630003"
EMOJI_FULL_CONN = "5312536423851630004"
EMOJI_BIZ_CONN = "5312536423851630005"
EMOJI_BACK = "5312536423851630006"
EMOJI_COPY = "5312536423851630007"
EMOJI_SETTINGS = "5312536423851630008"
EMOJI_CHECK = "5312536423851630009"
EMOJI_ON = "5312536423851630010"
EMOJI_OFF = "5312536423851630011"
EMOJI_STOP = "5312536423851630012"

WELCOME_TEXT = (
    "🔥 <b>TrackerZaki</b> — сервис для сохранения удалённых и отредактированных сообщений.\n\n"
    "<blockquote>"
    "Чтобы сохранить сгорающее сообщение — ответь на него любым сообщением.\n"
    "<i>напр. «Чуть позже гляну»</i>"
    "</blockquote>"
)

CONNECT_TEXT = (
    "🔌 <b>Выбери способ подключения</b>\n\n"
    "<blockquote>"
    "• <b>Business Connection</b> — быстро, безопасно, без входа в аккаунт.\n"
    "• <b>Full Connection</b> — через сессию, с мониторингом активности."
    "</blockquote>"
)

BUSINESS_TEXT = (
    "💼 <b>Business Connection</b>\n\n"
    "<blockquote>"
    "1. Нажми <b>«Скопировать»</b> ниже.\n"
    "2. Открой <b>Настройки → Мой аккаунт → Изменить → Автоматизация чатов</b>.\n"
    "3. Вставь <b>@TrackerZaki_Bot</b> и сохрани."
    "</blockquote>"
)


def setup_start_handlers(shared_session_manager, tracker_service, savemod_service, user_bot_service):
    global _session_manager, _tracker_service, _savemod_service, _user_bot_service
    _session_manager = shared_session_manager
    _tracker_service = tracker_service
    _savemod_service = savemod_service
    _user_bot_service = user_bot_service


# ─────────────────────── RICH MESSAGE BUTTONS ─────────────────────────── #

def get_welcome_keyboard() -> list[str]:
    return [
        _button_row(
            _rich_button("🔌 Подключить", callback_data="open_connect", style="primary"),
        ),
        _button_row(
            _rich_button("📖 Инструкция", url="https://teletype.in/@zakiiq/yJ1Gx4dEEV5", style="success"),
            _rich_button("🤖 Создать бота", callback_data="create_bot", style="success"),
        ),

    ]


def get_connect_keyboard() -> list[str]:
    return [
        _button_row(_rich_button("🔐 Full Connection", callback_data="agree", style="primary")),
        _button_row(_rich_button("💼 Business Connection", callback_data="mode_business", style="success")),
        _button_row(_rich_button("⬅️ Назад", callback_data="back_welcome")),
    ]


def get_business_keyboard() -> list[str]:
    return [
        _button_row(
            _rich_button("📋 Скопировать", copy_text=BOT_USERNAME_TAG, style="primary"),
            _rich_button("⚙️ Настройки", url="tg://settings/", style="primary"),
        ),
        _button_row(_rich_button("✅ Проверить подключение", callback_data="check_bc", style="success")),
        _button_row(_rich_button("⬅️ Назад", callback_data="open_connect")),
    ]


def get_profile_keyboard(user: UserSession) -> list[str]:
    buttons = []

    if user.savemod_enabled:
        buttons.append(_button_row(
            _rich_button("⏻ Выключить SaveMod", callback_data="toggle_savemod", style="danger")
        ))
    else:
        buttons.append(_button_row(
            _rich_button("✓ Включить SaveMod", callback_data="toggle_savemod", style="success")
        ))

    buttons.append(_button_row(
        _rich_button("🤖 Добавить бота", callback_data="create_bot", style="primary")
    ))

    if getattr(user, "connection_type", "full") == "full" and tasks.is_tracker_running(user.bot_user_id):
        buttons.append(_button_row(
            _rich_button("⏹ Остановить Трекер", callback_data="stop_tracker", style="danger")
        ))

    return buttons


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


async def safe_edit(message: Message, text: str, buttons=None):
    """Обновляет Rich Message, включая встроенные в него кнопки."""
    html = text
    if buttons:
        html += "\\n\\n" + "\\n".join(buttons)

    try:
        await message.bot(EditRichMessageText(
            chat_id=message.chat.id,
            message_id=message.message_id,
            rich_message={"html": html},
        ))
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
        # Профиль — обычный текст (здесь фото уже не нужно)
        await send_rich_message(
            message.bot,
            message.chat.id,
            _build_profile_text(user_id, user, my_bots)
            + "".join(get_profile_keyboard(user)),
        )
        return

    # Главное меню — Rich Message: кнопки являются частью самого сообщения.
    photo = FSInputFile("Png/starttutor.png")
    welcome_html = (
        '<img src="tg://photo?id=start_cover"/>'
        + WELCOME_TEXT
        + "".join(get_welcome_keyboard())
    )
    await send_rich_message(message.bot, message.chat.id, welcome_html, media=photo)


@router.callback_query(F.data == "back_welcome")
async def callback_back_welcome(callback: CallbackQuery):
    await callback.answer()
    # Переключаем содержимое Rich Message вместе со встроенными кнопками.
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
