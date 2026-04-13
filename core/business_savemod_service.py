"""
SaveMod для Business Connection.

ВАЖНО: в aiogram хендлеры нельзя вешать через @router внутри класса —
декоратор регистрирует функцию до создания экземпляра, self недоступен.
Решение: хендлеры — обычные функции вне класса, которые вызывают методы
глобального экземпляра сервиса.
"""

from datetime import datetime
from io import BytesIO

from aiogram import Router, Bot
from aiogram.types import Message, BusinessMessagesDeleted, BufferedInputFile
from sqlalchemy import select

from db.session import AsyncSessionLocal
from db.models import SavedMessage, UserSession

router = Router()

LOG_CHANNEL_ID = -1003711524247


class BusinessSaveModService:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._registry: dict[str, int] = {}     # bc_id → owner_id
        self._names_cache: dict[int, str] = {}  # entity_id → name

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
            return result.scalar_one_or_none()

    async def get_entity_name(self, entity_id: int) -> str:
        if not entity_id:
            return "Неизвестно"
        if entity_id in self._names_cache:
            return self._names_cache[entity_id]
        try:
            chat = await self.bot.get_chat(entity_id)
            name = chat.full_name or f"ID:{entity_id}"
        except Exception:
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

    async def format_logs_to_txt(self, owner_id: int) -> str | None:
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
            chat_name = await self.get_entity_name(chat_id)
            out += f"👉 ДИАЛОГ С: {chat_name} (ID: {chat_id})\n"
            out += "-" * 40 + "\n"

            for log in sorted(chat_logs, key=lambda x: x.date or 0):
                t = datetime.fromtimestamp(log.date).strftime("%d.%m %H:%M") if log.date else "???"
                sender_name = await self.get_entity_name(log.sender_id)
                p = "[ВЫ]" if log.sender_id == owner_id else "[ОН]"
                out += f"[{t}] {p} {sender_name}\n"
                if log.text:
                    out += f"   {log.text}\n"
                if log.file_id:
                    out += f"   [Медиа]\n"
                out += "\n"

            out += "=" * 60 + "\n\n"

        return out

    def _detect_media_type(self, message: Message) -> str | None:
        """Определяет тип медиа. video_note ОБЯЗАТЕЛЬНО раньше video."""
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
        """Проверяет самоуничтожающееся медиа."""
        if message.photo and getattr(message.photo[-1], 'ttl_seconds', None):
            return True
        if message.video and getattr(message.video, 'ttl_seconds', None):
            return True
        # aiogram также может выставить has_media_spoiler для скрытых медиа
        if getattr(message, 'has_media_spoiler', False):
            return True
        return False

    async def _save_media_to_log(self, message: Message, owner_id: int, prefix: str = "") -> str | None:
        """Скачивает медиа, сохраняет в лог-канал, возвращает file_id."""
        media_type = self._detect_media_type(message)
        if not media_type:
            return None

        try:
            # Определяем объект для скачивания — photo[-1] только если список непустой
            if media_type == "photo":
                media_obj = message.photo[-1] if message.photo else None
            elif media_type == "video_note":
                media_obj = message.video_note
            elif media_type == "voice":
                media_obj = message.voice
            elif media_type == "video":
                media_obj = message.video
            elif media_type == "audio":
                media_obj = message.audio
            elif media_type == "document":
                media_obj = message.document
            elif media_type == "sticker":
                media_obj = message.sticker
            elif media_type == "animation":
                media_obj = message.animation
            else:
                media_obj = None

            if not media_obj:
                return None

            file_bytes: BytesIO = await self.bot.download(media_obj)
            if not file_bytes:
                return None

            # Читаем байты один раз
            raw = file_bytes.read()

            sender_id = message.from_user.id if message.from_user else 0
            sender_name = await self.get_entity_name(sender_id)

            caption = (
                f"{prefix}"
                f"📁 <b>Новое медиа в архиве</b>\n"
                f"👤 <b>От:</b> {sender_name} (ID: <code>{sender_id}</code>)\n"
                f"🎯 <b>Аккаунт:</b> <code>{owner_id}</code>\n"
                f"🕒 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}"
            )

            input_file = BufferedInputFile(raw, filename="media")

            # Кружки не поддерживают caption — отправляем отдельным сообщением
            if media_type == "video_note":
                sent = await self.bot.send_video_note(LOG_CHANNEL_ID, video_note=input_file)
                await self.bot.send_message(LOG_CHANNEL_ID, f"☝️ <b>Кружок выше:</b>\n{caption}", parse_mode="HTML")
                return sent.video_note.file_id

            if media_type == "photo":
                sent = await self.bot.send_photo(LOG_CHANNEL_ID, photo=input_file, caption=caption, parse_mode="HTML")
                return sent.photo[-1].file_id
            elif media_type == "voice":
                sent = await self.bot.send_voice(LOG_CHANNEL_ID, voice=input_file, caption=caption, parse_mode="HTML")
                return sent.voice.file_id
            elif media_type == "video":
                sent = await self.bot.send_video(LOG_CHANNEL_ID, video=input_file, caption=caption, parse_mode="HTML")
                return sent.video.file_id
            elif media_type == "audio":
                sent = await self.bot.send_audio(LOG_CHANNEL_ID, audio=input_file, caption=caption, parse_mode="HTML")
                return sent.audio.file_id
            else:
                # document, sticker, animation
                sent = await self.bot.send_document(LOG_CHANNEL_ID, document=input_file, caption=caption, parse_mode="HTML")
                return sent.document.file_id

        except Exception as e:
            print(f"[BusinessSaveMod] Ошибка сохранения медиа: {e}")
        return None

    async def _send_deleted_to_user(self, owner_id: int, saved: SavedMessage, info_text: str):
        """Отправляет удалённое сообщение владельцу.
        Если есть медиа — шлём файл с caption (одно сообщение).
        Кружки caption не поддерживают — там два сообщения неизбежно.
        Если медиа нет — просто текст.
        """
        if not saved.file_id:
            await self.bot.send_message(owner_id, info_text, parse_mode="HTML")
            return

        # Пробуем отправить с caption — от наиболее вероятного типа
        send_order = [
            ("send_photo",    {"photo":    saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
            ("send_video",    {"video":    saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
            ("send_voice",    {"voice":    saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
            ("send_audio",    {"audio":    saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
            ("send_document", {"document": saved.file_id, "caption": info_text, "parse_mode": "HTML"}),
        ]

        for method_name, kwargs in send_order:
            try:
                await getattr(self.bot, method_name)(owner_id, **kwargs)
                return
            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ["wrong type", "type", "invalid"]):
                    continue
                print(f"[BusinessSaveMod] Не удалось переслать медиа ({method_name}): {e}")
                break

        # Кружок — caption не поддерживается, шлём отдельно
        try:
            await self.bot.send_video_note(owner_id, video_note=saved.file_id)
            await self.bot.send_message(owner_id, info_text, parse_mode="HTML")
        except Exception as e:
            print(f"[BusinessSaveMod] Fallback video_note тоже упал: {e}")
            await self.bot.send_message(owner_id, info_text, parse_mode="HTML")

    # ─────────────────── ОСНОВНАЯ ЛОГИКА ─────────────────── #

    async def handle_new_message(self, message: Message):
        bc_id = message.business_connection_id
        owner_id = self.get_owner(bc_id)
        if not owner_id or not await self._is_savemod_active(owner_id):
            return

        if await self._get_saved(owner_id, message.chat.id, message.message_id):
            return  # дубль

        text = message.text or message.caption or ""
        is_ttl = self._check_ttl(message)
        media_type = self._detect_media_type(message)
        prefix = "🔥 <b>САМОУНИЧТОЖАЮЩЕЕСЯ МЕДИА</b>\n" if is_ttl else ""

        sender_id = message.from_user.id if message.from_user else 0

        # Для TTL — алерт отправляем СРАЗУ, до попытки скачать.
        # Telegram может не дать скачать TTL медиа через Bot API.
        if is_ttl:
            sender_name = await self.get_entity_name(sender_id)
            ttl_text = (
                f"🔥 <b>Самоуничтожающееся сообщение</b>\n\n"
                f"<blockquote>"
                f"<b>От: <a href=\"tg://user?id={sender_id}\">{sender_name}</a></b>\n"
                f"</blockquote>\n"
                f"<b>@TrackerZaki_Bot</b>"
            )
            try:
                await self.bot.send_message(chat_id=owner_id, text=ttl_text, parse_mode="HTML")
            except Exception as e:
                print(f"[BusinessSaveMod] Ошибка отправки TTL алерта: {e}")

        file_id = None
        if media_type:
            file_id = await self._save_media_to_log(message, owner_id, prefix)

        # Если удалось скачать TTL медиа — дополнительно шлём сам файл
        if is_ttl and file_id:
            try:
                if media_type == "video_note":
                    await self.bot.send_video_note(chat_id=owner_id, video_note=file_id)
                elif media_type == "photo":
                    await self.bot.send_photo(chat_id=owner_id, photo=file_id)
                elif media_type == "voice":
                    await self.bot.send_voice(chat_id=owner_id, voice=file_id)
                elif media_type == "video":
                    await self.bot.send_video(chat_id=owner_id, video=file_id)
                else:
                    await self.bot.send_document(chat_id=owner_id, document=file_id)
            except Exception as e:
                print(f"[BusinessSaveMod] Ошибка пересылки TTL медиа: {e}")

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
            saved = result.scalar_one_or_none()
            if not saved or saved.text == new_text:
                return

            old_text = saved.text or ""
            saved.text = new_text
            await session.commit()

        sender_name = await self.get_entity_name(saved.sender_id)

        await self.bot.send_message(
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
                await self.bot.send_message(
                    owner_id,
                    f"🗑 Удалено сообщение (ID {msg_id})\n"
                    f"Чат: <code>{event.chat.id}</code>\n"
                    f"<i>Текст не был сохранён</i>\n\n"
                    f"<b>@TrackerZaki_Bot</b>",
                    parse_mode="HTML",
                )
                continue

            sender_name = await self.get_entity_name(saved.sender_id)

            info_text = (
                f"🗑 <b>Удалённое сообщение</b>\n\n"
                f"<blockquote>"
                f"<b><a href=\"tg://user?id={saved.sender_id}\">{sender_name}</a></b>\n"
                f"{saved.text or ""}"
                f"</blockquote>"
                f"<b>@TrackerZaki_Bot</b>"
            )

            
            # Медиа + текст в одном сообщении через caption
            await self._send_deleted_to_user(owner_id, saved, info_text)


# ─────────────────── ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ─────────────────── #

_service: BusinessSaveModService | None = None


def init_business_savemod(bot: Bot) -> BusinessSaveModService:
    global _service
    _service = BusinessSaveModService(bot)
    return _service


def get_service() -> BusinessSaveModService:
    if _service is None:
        raise RuntimeError("BusinessSaveModService не инициализирован. Вызови init_business_savemod(bot) при старте.")
    return _service

@router.business_connection()
async def on_business_connection(connection: BusinessMessagesDeleted, bot: Bot):
    # Когда юзер подключает бота в настройках ТГ Бизнес
    if connection.is_enabled:
        async with AsyncSessionLocal() as session:
            # Обновляем сессию пользователя, записывая туда ID подключения
            await session.execute(
                update(UserSession)
                .where(UserSession.bot_user_id == connection.user_id)
                .values(
                    business_connection_id=connection.id,
                    connection_type="business"
                )
            )
            await session.commit()
        
        # Сразу регистрируем в локальном реестре сервиса, чтобы не ждать перезагрузки
        get_service().register_connection(connection.id, connection.user_id)
        
        await bot.send_message(connection.user_id, "✅ Бизнес-подключение успешно активировано!")




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
