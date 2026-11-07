# core/business_savemod_service.py
"""
SaveMod для Business Connection (Универсальный для Multibot режима).
"""
from jinja2 import Environment, FileSystemLoader
import os
import asyncio
import base64
import binascii
import logging
from collections import OrderedDict
from aiohttp import ClientError
from aiogram.exceptions import TelegramAPIError

from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO

from aiogram import Router, Bot
from aiogram.types import Message, BusinessMessagesDeleted, BufferedInputFile
from sqlalchemy import select

from db.session import AsyncSessionLocal
from db.models import SavedMessage, UserSession
from html import escape
from aiogram.types import LinkPreviewOptions

router = Router()

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1004327024615"))

logger = logging.getLogger(__name__)
REPLY_MEDIA_MAX_BYTES = 10 * 1024 * 1024
# Значения TDLib FileType для SelfDestructingVideoNote и SelfDestructingVoiceNote.
REPLY_PLAY_ONCE_TYPES = {"video_note": 24, "voice": 25}
REPLY_MEDIA_FILENAMES = {"photo": "photo.jpg", "video_note": "video_note.mp4", "voice": "voice.ogg"}


def _telegram_file_type(file_id: str) -> int | None:
    """Читает тип из TDLib remote file_id (форматы 2 и 4).

    Источники: tdlib/td, files/FileManager.cpp, FileLocation.hpp, FileType.h.
    Типы: Photo=2, SelfDestructingPhoto=22. Неизвестный формат — None.
    file_id не является документированным публичным контрактом Bot API.
    """
    if not isinstance(file_id, str) or not 4 <= len(file_id) <= 4096:
        return None
    try:
        packed = base64.b64decode(file_id + '=' * (-len(file_id) % 4), altchars=b'-_', validate=True)
    except (ValueError, binascii.Error):
        return None
    if not packed:
        return None
    if packed[-1] == 4:
        packed = packed[:-2]  # Версия сериализации и версия persistent ID.
    elif packed[-1] == 2:
        packed = packed[:-1]
    else:
        return None
    decoded = bytearray()
    index = 0
    while index < len(packed):
        value = packed[index]
        index += 1
        if value == 0:
            if index >= len(packed) or packed[index] == 0:
                return None
            decoded.extend(b'\x00' * packed[index])
            index += 1
        else:
            decoded.append(value)
        if len(decoded) > 16384:
            return None
    if len(decoded) < 8:
        return None
    raw_type = int.from_bytes(decoded[:4], 'little')
    return raw_type & ~((1 << 24) | (1 << 25))


class _ReplyMediaBuffer(BytesIO):
    def write(self, data):
        if self.tell() + len(data) > REPLY_MEDIA_MAX_BYTES:
            raise ValueError('Превышен лимит медиа 10 МиБ')
        return super().write(data)


class BusinessSaveModService:
    def __init__(self, bot: Bot):
        self.bot = bot  # Это Главный бот (используется как fallback и для лог-канала)
        self._registry: dict[str, int] = {}     # bc_id → owner_id
        self._names_cache: dict[int, str] = {}  # entity_id → name

        self._reply_media_enabled = os.getenv('BUSINESS_REPLY_PHOTO_ENABLED', 'false').lower() == 'true'
        self._reply_media_diagnostics = os.getenv('BUSINESS_REPLY_PHOTO_DIAGNOSTICS', 'false').lower() == 'true'
        self._reply_media_owner_ids = {
            int(value.strip()) for value in os.getenv('BUSINESS_REPLY_PHOTO_OWNER_IDS', '').split(',')
            if value.strip()
        }
        self._reply_media_lock = asyncio.Lock()
        self._reply_media_saved = OrderedDict()

    # ─────────────────── МЕДИА ИЗ ОТВЕТА ВЛАДЕЛЬЦА ─────────────────── #

    async def _reply_media_notice(self, bot, owner_id, text, *, failed=False):
        # Не печатаем ответы API целиком: они могут содержать адрес файла или токен.
        if failed:
            logger.warning('[ReplyMedia] %s', text)
        if not self._reply_media_diagnostics:
            return
        try:
            await bot.send_message(owner_id, text)
        except TelegramAPIError:
            logger.warning('[ReplyMedia] Не доставлена диагностика владельцу')

    async def _send_reply_media(self, bot, chat_id, media_type, raw, caption) -> Message:
        upload = BufferedInputFile(raw, filename=REPLY_MEDIA_FILENAMES[media_type])
        if media_type == 'video_note':
            sent = await bot.send_video_note(chat_id, video_note=upload)
            try:
                await bot.send_message(chat_id, caption, parse_mode='HTML', reply_to_message_id=sent.message_id,link_preview_options=LinkPreviewOptions(is_disabled=True) )
            except (TelegramAPIError, ClientError, OSError, asyncio.TimeoutError):
                logger.warning('[ReplyMedia] Не удалось отправить подпись к кружку')
            return sent
        if media_type == 'voice':
            return await bot.send_voice(chat_id, voice=upload, caption=caption, parse_mode='HTML')
        return await bot.send_photo(chat_id, photo=upload, caption=caption, parse_mode='HTML')

    async def _deliver_reply_media(self, archived: Message, owner_id: int, receiving_bot: Bot,
                                   media_type: str, user_caption: str, raw: bytes | None = None) -> bool:
        try:
            if raw is None:
                media = archived.photo[-1] if media_type == 'photo' and archived.photo else getattr(archived, media_type)
                if not media:
                    raise ValueError('В архивном сообщении отсутствует медиа')
                with _ReplyMediaBuffer() as buffer:
                    await self.bot.download(media, destination=buffer, timeout=60)
                    raw = buffer.getvalue()
                if not raw:
                    raise ValueError('Архивный файл пуст')
            await self._send_reply_media(receiving_bot, owner_id, media_type, raw, user_caption)
        except (TelegramAPIError, ClientError, OSError, ValueError, asyncio.TimeoutError):
            return False
        return True

    async def _save_reply_media(self, message: Message, owner_id: int):
        if not self._reply_media_enabled or (self._reply_media_owner_ids and owner_id not in self._reply_media_owner_ids):
            return
        if not message.from_user or message.from_user.id != owner_id or message.sender_business_bot:
            return
        if not message.business_connection_id:
            return
        original = message.reply_to_message
        if not original:
            return
        media_type = self._detect_media_type(original)
        if media_type == 'photo':
            if not self._check_ttl(original):
                return
            media = original.photo[-1]
        elif media_type in REPLY_PLAY_ONCE_TYPES:
            media = getattr(original, media_type)
            if _telegram_file_type(media.file_id) != REPLY_PLAY_ONCE_TYPES[media_type]:
                return
        else:
            return
        download_bot = message.bot
        try:
            connection = await download_bot.get_business_connection(message.business_connection_id)
        except TelegramAPIError:
            await self._reply_media_notice(download_bot, owner_id, 'Не удалось проверить бизнес-подключение.', failed=True)
            return
        if connection.user.id != owner_id or not connection.is_enabled:
            return
        key = (download_bot.id, message.business_connection_id, owner_id, message.chat.id, original.message_id)
        # Последовательная обработка исключает двойную отправку одновременных ответов в этом процессе.
        async with self._reply_media_lock:
            cached = self._reply_media_saved.get(key)
            if cached is not None:
                if not cached['delivered']:
                    cached['delivered'] = await self._deliver_reply_media(
                        cached['archive'], owner_id, download_bot, media_type, cached['caption'],
                    )
                return
            if media.file_size is not None and media.file_size > REPLY_MEDIA_MAX_BYTES:
                await self._reply_media_notice(download_bot, owner_id, 'Медиа превышает лимит 10 МиБ.', failed=True)
                return
            try:
                remote = await download_bot.get_file(media.file_id)
            except TelegramAPIError:
                await self._reply_media_notice(download_bot, owner_id, 'getFile отклонён Telegram: медиа не сохранено.', failed=True)
                return
            if not remote.file_path:
                await self._reply_media_notice(download_bot, owner_id, 'getFile не вернул file_path: медиа не сохранено.', failed=True)
                return
            if remote.file_size is not None and remote.file_size > REPLY_MEDIA_MAX_BYTES:
                await self._reply_media_notice(download_bot, owner_id, 'Файл превышает лимит 10 МиБ.', failed=True)
                return
            with _ReplyMediaBuffer() as buffer:
                try:
                    await download_bot.download_file(remote.file_path, destination=buffer, timeout=60)
                except (TelegramAPIError, ClientError, OSError, ValueError, asyncio.TimeoutError):
                    await self._reply_media_notice(download_bot, owner_id, 'Не удалось скачать медиа после getFile.', failed=True)
                    return
                if buffer.getbuffer().nbytes == 0:
                    await self._reply_media_notice(download_bot, owner_id, 'Telegram вернул пустой файл.', failed=True)
                    return
                sender = original.from_user
                sender_chat = original.sender_chat
                sender_id = sender.id if sender else (sender_chat.id if sender_chat else None)
                sender_name = sender.full_name if sender else (sender_chat.title if sender_chat else 'Неизвестно')
                owner_name = connection.user.full_name
                
                # 1. Текст для архивного канала (оставляем техническим)
                archive_caption = (
                    '🔥 <b>САМОУНИЧТОЖАЮЩЕЕСЯ МЕДИА</b>\n'
                    '📁 <b>Новое медиа в архиве</b>\n'
                    f'👤 <b>От:</b> {escape((sender_name or "Неизвестно")[:200])} '
                    f'(ID: <code>{sender_id if sender_id is not None else "неизвестен"}</code>)\n'
                    f'🎯 <b>Аккаунт:</b> {escape(owner_name[:200])} (ID: <code>{owner_id}</code>)\n'
                    f'🕒 <b>Время:</b> {datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M:%S")}'
                )

                # 2. Текст для пользователя в бота (ваш красивый стиль с цитатой)
                safe_text = escape(original.caption or '')
                user_caption = (
                    f"🔥 <b>Самоуничтожающееся медиа</b>\n\n"
                    f"<blockquote>"
                    f"<b><a href='tg://user?id={sender_id}'>{escape((sender_name or 'Неизвестно')[:200])}</a></b>\n"
                    f"{safe_text}"
                    f"</blockquote>\n"
                    f'<b><a href="https://t.me/TrackerZaki_Bot">TrackerZaki_Bot</a></b>'
                )

                raw = buffer.getvalue()
                try:
                    archived = await self._send_reply_media(
                        self.bot, LOG_CHANNEL_ID, media_type, raw, archive_caption,
                    )
                except (TelegramAPIError, ClientError, OSError, asyncio.TimeoutError):
                    return
                
                # Сохраняем в кэш и архивный объект, и user_caption
                cached = {'archive': archived, 'caption': user_caption, 'delivered': False}
                self._reply_media_saved[key] = cached
                if len(self._reply_media_saved) > 1000:
                    self._reply_media_saved.popitem(last=False)
                
                # Доставляем владельцу с вашим красивым user_caption
                cached['delivered'] = await self._deliver_reply_media(
                    archived, owner_id, download_bot, media_type, user_caption, raw=raw,
                )

    # ─────────────────── РЕЕСТР ─────────────────── #

    async def load_registry(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSession).where(
                    UserSession.connection_type == "business",
                    UserSession.business_connection_id.is_not(None),
                )
            )
            users = result.scalars().all()

        for user in users:
            self._registry[user.business_connection_id] = user.bot_user_id

        print(f"[BusinessSaveMod] Загружено {len(self._registry)} подключений")

    def register_connection(self, bc_id: str, user_id: int):
        self._registry[bc_id] = user_id
        print(f"[BusinessSaveMod] Зарегистрирован: {bc_id} → {user_id}")

    def get_owner(self, bc_id: str) -> int | None:
        return self._registry.get(bc_id)

    # ─────────────────── ВСПОМОГАТЕЛЬНЫЕ ─────────────────── #

    async def _is_savemod_active(self, owner_id: int) -> bool:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSession).where(UserSession.bot_user_id == owner_id)
            )
            user = result.scalar_one_or_none()
        return bool(user and user.savemod_enabled)

    async def _get_saved(self, owner_id: int, chat_id: int, msg_id: int) -> SavedMessage | None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SavedMessage).where(
                    SavedMessage.owner_bot_id == owner_id,
                    SavedMessage.chat_id == chat_id,
                    SavedMessage.message_id == msg_id,
                )
            )
            return result.scalars().first()

    async def get_entity_name(self, entity_id: int, bot: Bot = None) -> str:
        """Получает имя чата через переданного активного бота (или главного бота)"""
        if not entity_id:
            return "Неизвестно"
    
        if entity_id in self._names_cache:
            return self._names_cache[entity_id]
    
        active_bot = bot or self.bot
        try:
            chat = await active_bot.get_chat(entity_id)
    
            if chat.full_name:
                name = chat.full_name
            elif chat.title:
                name = chat.title
            elif chat.username:
                name = f"@{chat.username}"
            else:
                first = chat.first_name or ""
                last = chat.last_name or ""
                name = (first + " " + last).strip()
    
            if not name:
                name = f"ID:{entity_id}"
    
        except Exception as e:
            print(f"[get_entity_name] ошибка: {e}")
            name = f"ID:{entity_id}"
    
        self._names_cache[entity_id] = name
        return name

    async def get_user_logs(self, owner_id: int):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SavedMessage)
                .where(SavedMessage.owner_bot_id == owner_id)
                .order_by(SavedMessage.date.desc())
            )
            return result.scalars().all()

    async def format_logs_to_txt(self, owner_id: int, bot: Bot = None) -> str | None:
        logs = await self.get_user_logs(owner_id)
        if not logs:
            return None

        grouped: dict[int, list] = {}
        for log in logs:
            grouped.setdefault(log.chat_id, []).append(log)

        out = "АРХИВ ПЕРЕПИСКИ (Business Connection)\n"
        out += f"Владелец: {owner_id}\n"
        out += f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        out += "=" * 60 + "\n\n"

        for chat_id, chat_logs in grouped.items():
            chat_name = await self.get_entity_name(chat_id, bot=bot)
            out += f"👉 ДИАЛОГ С: {chat_name} (ID: {chat_id})\n"
            out += "-" * 40 + "\n"

            for log in sorted(chat_logs, key=lambda x: x.date or 0):
                t = datetime.fromtimestamp(log.date).strftime("%d.%m %H:%M") if log.date else "???"
                sender_name = await self.get_entity_name(log.sender_id, bot=bot)
                p = "[ВЫ]" if log.sender_id == owner_id else "[ОН]"
                out += f"[{t}] {p} {sender_name}\n"
                if log.text:
                    out += f"   {log.text}\n"
                if log.file_id:
                    out += f"   [Медиа]\n"
                out += "\n"

            out += "=" * 60 + "\n\n"

        return out
    async def format_logs_to_html(self, owner_id: int, bot: Bot = None) -> str | None:
        logs = await self.get_user_logs(owner_id)
        if not logs:
            return None
    
        grouped = {}
    
        for log in logs:
            grouped.setdefault(log.chat_id, []).append(log)
    
        chats = []
    
        for chat_id, chat_logs in grouped.items():
            chat_name = await self.get_entity_name(chat_id, bot)
    
            messages = []
    
            for log in sorted(chat_logs, key=lambda x: x.date or 0):
            
                sender_name = await self.get_entity_name(log.sender_id, bot)
    
                messages.append({
                    "sender": sender_name,
                    "is_me": log.sender_id == owner_id,
                    "text": escape(log.text or ""),
                    "time": datetime.fromtimestamp(
                        log.date
                    ).strftime("%d.%m.%Y %H:%M") if log.date else "",
                    "media": bool(log.file_id)
                })
    
            chats.append({
                "id": chat_id,
                "name": chat_name,
                "messages": messages
            })
    
        env = Environment(
            loader=FileSystemLoader(
                os.path.join(os.getcwd(), "templates")
            ),
            autoescape=True
        )
    
        template = env.get_template("logs.html")
    
        html = template.render(
            generated=datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            owner=owner_id,
            chats=chats
        )
    
        return html
    def _detect_media_type(self, message: Message) -> str | None:
        if message.video_note:    return "video_note"
        if message.photo:         return "photo"
        if message.voice:         return "voice"
        if message.video:         return "video"
        if message.audio:         return "audio"
        if message.document:      return "document"
        if message.sticker:       return "sticker"
        if message.animation:     return "animation"
        return None

    def _check_ttl(self, message: Message) -> bool:
        if message.photo:
            photo = message.photo[-1]
            if _telegram_file_type(photo.file_id) == 22:
                return True
            # На случай, если Telegram явно передаст TTL в объекте медиа.
            ttl = getattr(photo, 'ttl_seconds', None)
            if isinstance(ttl, int) and ttl > 0:
                return True
        if message.video and getattr(message.video, 'ttl_seconds', None):
            return True
        return False

    async def _save_media_to_log(self, message: Message, owner_id: int, prefix: str = "") -> str | None:
        """Скачивает медиа через бота-получателя, льет в канал через Главного бота, возвращает оригинальный file_id."""
        media_type = self._detect_media_type(message)
        if not media_type:
            return None
        # Временное фото сохраняет только обработчик ответа владельца.
        if message.photo and self._check_ttl(message):
            return None

        try:
            if media_type == "photo": media_obj = message.photo[-1] if message.photo else None
            elif media_type == "video_note": media_obj = message.video_note
            elif media_type == "voice": media_obj = message.voice
            elif media_type == "video": media_obj = message.video
            elif media_type == "audio": media_obj = message.audio
            elif media_type == "document": media_obj = message.document
            elif media_type == "sticker": media_obj = message.sticker
            elif media_type == "animation": media_obj = message.animation
            else: media_obj = None

            if not media_obj:
                return None

            # 🔥 Сохраняем ИСХОДНЫЙ file_id, который понимает текущий бот
            original_file_id = media_obj.file_id if media_type != "photo" else message.photo[-1].file_id

            # 🔥 Скачиваем строго через message.bot (у кастомного бота свой токен доступа к файлу!)
            file_bytes: BytesIO = await message.bot.download(media_obj)
            if not file_bytes:
                return original_file_id

            raw = file_bytes.read()
            sender_id = message.from_user.id if message.from_user else 0
            sender_name = await self.get_entity_name(sender_id, bot=message.bot)

            caption = (
                f"{prefix}"
                f"📁 <b>Новое медиа в архиве</b>\n"
                f"👤 <b>От:</b> {sender_name} (ID: <code>{sender_id}</code>)\n"
                f"🎯 <b>Аккаунт:</b> <code>{owner_id}</code>\n"
                f"🕒 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}"
            )

            input_file = BufferedInputFile(raw, filename="media")

            # 🔥 В лог-канал отправляем ВСЕГДА через Главного бота (self.bot)
            if media_type == "video_note":
                await self.bot.send_video_note(LOG_CHANNEL_ID, video_note=input_file)
                await self.bot.send_message(LOG_CHANNEL_ID, f"☝️ <b>Кружок выше:</b>\n{caption}", parse_mode="HTML")
            elif media_type == "photo":
                await self.bot.send_photo(LOG_CHANNEL_ID, photo=input_file, caption=caption, parse_mode="HTML")
            elif media_type == "voice":
                await self.bot.send_voice(LOG_CHANNEL_ID, voice=input_file, caption=caption, parse_mode="HTML")
            elif media_type == "video":
                await self.bot.send_video(LOG_CHANNEL_ID, video=input_file, caption=caption, parse_mode="HTML")
            elif media_type == "audio":
                await self.bot.send_audio(LOG_CHANNEL_ID, audio=input_file, caption=caption, parse_mode="HTML")
            else:
                await self.bot.send_document(LOG_CHANNEL_ID, document=input_file, caption=caption, parse_mode="HTML")

            # Возвращаем исходный ID для сохранения в БД под этого конкретного бота
            return original_file_id

        except Exception as e:
            print(f"[BusinessSaveMod] Ошибка сохранения медиа: {e}")
            # Если отправка в канал упала, всё равно пытаемся вернуть оригинальный file_id для работы внутри бота
            try: return media_obj.file_id if media_type != "photo" else message.photo[-1].file_id
            except: return None

    async def _send_deleted_to_user(self, owner_id: int, saved: SavedMessage, info_text: str, bot: Bot):
        """Отправляет удалённое сообщение владельцу строго через активного бота (bot)."""
        if not saved.file_id:
            await bot.send_message(owner_id, info_text, parse_mode="HTML")
            return

        try:
            await bot.send_video_note(owner_id, video_note=saved.file_id)
            await bot.send_message(owner_id, info_text, parse_mode="HTML")
            return
        except Exception as e:
            pass

        send_order = [
            ("send_photo",    {"photo":    saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
            ("send_video",    {"video":    saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
            ("send_voice",    {"voice":    saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
            ("send_audio",    {"audio":    saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
            ("send_document", {"document": saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
        ]

        for method_name, kwargs in send_order:
            try:
                # 🔥 Вызываем метод у динамического бота (bot)
                await getattr(bot, method_name)(owner_id, **kwargs)
                return
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ["wrong type", "type", "invalid remote file"]):
                    continue
                print(f"[BusinessSaveMod] Не удалось переслать медиа ({method_name}): {e}")
                break

        # Кружок
        await bot.send_message(owner_id, info_text, parse_mode="HTML")

    # ─────────────────── ОСНОВНАЯ ЛОГИКА ─────────────────── #

    async def handle_new_message(self, message: Message):
        bc_id = message.business_connection_id
        owner_id = self.get_owner(bc_id)
        if not owner_id or not await self._is_savemod_active(owner_id):
            return

        await self._save_reply_media(message, owner_id)

        if await self._get_saved(owner_id, message.chat.id, message.message_id):
            return  

        text = message.text or message.caption or ""
        is_ttl = self._check_ttl(message)
        media_type = self._detect_media_type(message)
        prefix = "🔥 <b>САМОУНИЧТОЖАЮЩЕЕСЯ МЕДИА</b>\n" if is_ttl else ""

        sender_id = message.from_user.id if message.from_user else 0
        sender_name = await self.get_entity_name(sender_id, bot=message.bot)

        # 1. Сначала сохраняем медиа в лог-канал (если оно есть)
        file_id = None
        if media_type:
            file_id = await self._save_media_to_log(message, owner_id, prefix)

        # 2. Формируем единый красивый стиль уведомления для владельца
        if is_ttl:
            safe_text = escape(text)
            # Стиль подписи идентичен стилю удаленных сообщений
            ttl_caption = (
                f"🔥 <b>Самоуничтожающееся медиа</b>\n\n"
                f"<blockquote>"
                f"<b><a href='tg://user?id={sender_id}'>{sender_name}</a></b>\n"
                f"{safe_text}"
                f"</blockquote>\n"
                f'<b><a href="https://t.me/TrackerZaki_Bot">TrackerZaki_Bot</a></b>'
            )
            try:
                if file_id:
                    # Отправляем медиа СРАЗУ с красивой подписью-цитатой (без лишних текстовых алертов-дубликатов)
                    send_kwargs = {"chat_id": owner_id, "caption": ttl_caption, "parse_mode": "HTML"}
                    if media_type == "photo":
                        await message.bot.send_photo(photo=file_id, **send_kwargs)
                    elif media_type == "video":
                        await message.bot.send_video(video=file_id, **send_kwargs)
                    elif media_type == "voice":
                        await message.bot.send_voice(voice=file_id, **send_kwargs)
                    elif media_type == "audio":
                        await message.bot.send_audio(audio=file_id, **send_kwargs)
                    elif media_type == "video_note":
                        await message.bot.send_video_note(chat_id=owner_id, video_note=file_id)
                        await message.bot.send_message(chat_id=owner_id, text=ttl_caption, parse_mode="HTML")
                    else:
                        await message.bot.send_document(document=file_id, **send_kwargs)
                else:
                    # Если медиа не было, а был просто текст с таймером
                    await message.bot.send_message(chat_id=owner_id, text=ttl_caption, parse_mode="HTML")
            except Exception as e:
                print(f"[BusinessSaveMod] Ошибка отправки TTL уведомления: {e}")

        async with AsyncSessionLocal() as session:
            saved = SavedMessage(
                owner_bot_id=owner_id,
                chat_id=message.chat.id,
                message_id=message.message_id,
                sender_id=sender_id,
                text=text,
                date=int(message.date.timestamp()) if message.date else 0,
                file_id=file_id,
            )
            session.add(saved)
            await session.commit()

    async def handle_edited_message(self, message: Message):
        bc_id = message.business_connection_id
        owner_id = self.get_owner(bc_id)
        if not owner_id or not await self._is_savemod_active(owner_id):
            return

        new_text = message.text or message.caption or ""

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SavedMessage).where(
                    SavedMessage.owner_bot_id == owner_id,
                    SavedMessage.chat_id == message.chat.id,
                    SavedMessage.message_id == message.message_id,
                )
            )
            saved = result.scalars().first()
            if not saved or saved.text == new_text:
                return

            old_text = saved.text or ""
            saved.text = new_text
            await session.commit()

        sender_name = await self.get_entity_name(saved.sender_id, bot=message.bot)

        # 🔥 Отправляем через message.bot
        await message.bot.send_message(
            owner_id,
            f"🔏 <b>Сообщение отредактировано</b>\n\n"
            f"👤 От: <a href=\"tg://user?id={saved.sender_id}\">{sender_name}</a>\n\n"
            f"Старый:\n<blockquote>{old_text or '<i>пусто</i>'}</blockquote>\n\n"
            f"Новый:\n<blockquote>{new_text}</blockquote>\n\n"
            f"<b>@TrackerZaki_Bot</b>",
            parse_mode="HTML",
        )

    async def handle_deleted_messages(self, event: BusinessMessagesDeleted):
        bc_id = event.business_connection_id
        owner_id = self.get_owner(bc_id)
        if not owner_id or not await self._is_savemod_active(owner_id):
            return

        for msg_id in event.message_ids:
            saved = await self._get_saved(owner_id, event.chat.id, msg_id)

            if not saved:
                # 🔥 Отправляем через event.bot
                await event.bot.send_message(
                    owner_id,
                    f"🗑 Удалено сообщение (ID {msg_id})\n"
                    f"Чат: <code>{event.chat.id}</code>\n"
                    f"<i>Текст не был сохранён</i>\n\n"
                    f'<b><a href="https://t.me/TrackerZaki_Bot">TrackerZaki_Bot</a></b>\n\n',
                    parse_mode="HTML",
                )
                continue

            sender_name = await self.get_entity_name(saved.sender_id, bot=event.bot)

            safe_text = escape(saved.text or '')


            info_text = (
                f"🗑 <b>Удалённое сообщение</b>\n\n"
                f"<blockquote>"
                f"<b><a href='tg://user?id={saved.sender_id}'>{sender_name}</a></b>\n"
                f"{safe_text}"
                f"</blockquote>"
                f'<b><a href="tg://resolve?domain=TrackerZaki_Bot">@TrackerZaki_Bot</a></b>'
            )

            # 🔥 Передаем event.bot для отправки медиа/текста
            await self._send_deleted_to_user(owner_id, saved, info_text, bot=event.bot)


# ─────────────────── ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ─────────────────── #

_service: BusinessSaveModService | None = None


def init_business_savemod(bot: Bot) -> BusinessSaveModService:
    global _service
    _service = BusinessSaveModService(bot)
    return _service


def get_service() -> BusinessSaveModService:
    if _service is None:
        raise RuntimeError("BusinessSaveModService не инициализирован.")
    return _service


# ─────────────────── ХЕНДЛЕРЫ РОУТЕРА ─────────────────── #

@router.business_message()
async def on_business_message(message: Message):
    await get_service().handle_new_message(message)


@router.edited_business_message()
async def on_edited_business_message(message: Message):
    await get_service().handle_edited_message(message)


@router.deleted_business_messages()
async def on_deleted_business_messages(event: BusinessMessagesDeleted):
    await get_service().handle_deleted_messages(event)
