import os
import io
from datetime import datetime
from telethon import events
from sqlalchemy import event, select, or_
from aiogram.types import BufferedInputFile

from db.session import AsyncSessionLocal
from db.models import SavedMessage, UserSession

# ID вашего канала для логов медиа
LOG_CHANNEL_ID = -1003711524247 

class SaveModService:
    def __init__(self, bot, session_manager):
        self.bot = bot
        self.session_manager = session_manager
        self._attached_clients = set()
        self._names_cache = {} # Кэш имен для ускорения экспорта
        self._handlers = {}

    async def enable(self, bot_user_id: int):
        # 1. Пытаемся получить клиент
        client = await self.session_manager.get_client(bot_user_id)
        
        # 2. Если клиент не найден в памяти, пробуем восстановить его из БД
        if client is None:
            # Эта попытка заставит SessionManager заглянуть в БД и переподключить сессию
            client = await self.session_manager.get_client(bot_user_id)
            
        # 3. Если и после этого клиента нет — значит сессии реально не существует (нужен /auth)
        if client is None:
            raise RuntimeError("❌ Сначала авторизуйся (/auth)")

        # 4. Проверяем статус соединения (на случай, если клиент "завис")
        if not client.is_connected():
            await client.connect()

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSession).where(UserSession.bot_user_id == bot_user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                raise RuntimeError("❌ Пользователь не найден в БД")

            user.savemod_enabled = True
            await session.commit()

        # Подключаем хендлеры
        self._attach_handlers(client, bot_user_id)
        self._attached_clients.add(bot_user_id)

    async def disable(self, bot_user_id: int):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSession).where(UserSession.bot_user_id == bot_user_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.savemod_enabled = False
                await session.commit()
        client = await self.session_manager.get_client(bot_user_id)

        if client and bot_user_id in self._handlers:
            for handler in self._handlers[bot_user_id]:
                client.remove_event_handler(handler)
            del self._handlers[bot_user_id]

        # Удаляем из сета активных, чтобы при следующем включении хендлеры обновились
        if bot_user_id in self._attached_clients:
            self._attached_clients.remove(bot_user_id)

    # --- ОБРАБОТЧИКИ СОБЫТИЙ (Методы класса для исключения дублей) ---

# core/savemod_service.py

    async def on_new_message(self, event, client, owner_id):
        if not event.is_private or event.chat_id == 8418446543:
            return
    
        # 1. Сначала проверяем, нет ли уже такого сообщения в базе (от другого процесса)
        async with AsyncSessionLocal() as session:
            exists = await session.execute(
                select(SavedMessage).where(
                    SavedMessage.owner_bot_id == owner_id,
                    SavedMessage.message_id == event.id,
                    SavedMessage.chat_id == event.chat_id
                )
            )
            if exists.scalar():
                return # Если уже есть, выходим
        is_ttl = False
        if event.media: 
            if hasattr(event.media, 'ttl_seconds') and event.media.ttl_seconds:
                is_ttl = True
            elif hasattr(event.media, 'video') and getattr(event.media.video, 'ttl_seconds', None):
                is_ttl = True
        # 2. Только после этого работаем с медиа и сохраняем
        media_id = None
        if event.media:
            prefix = "🔥 <b>САМОУНИЧТОЖАЮЩЕЕСЯ МЕДИА</b>\n" if is_ttl else ""
            media_id = await self._forward_and_get_id(event, client, owner_id, prefix=prefix)
        
            if event.media and is_ttl:
                sender_name = await self.get_entity_name(client, event.sender_id)
                sender_link = f"https://t.me/{sender_name}" if sender_name else "https://t.me/unknown"
                text = (
                    f"🔥 <b>Самоуничтожающееся сообщение</b>\n\n"
                    f"<blockquote>"
                    f"<b>От: <a href=\"{sender_link}\">{sender_name}</a></b>\n"
                    f"</blockquote>\n"
                    f"@TrackerZaki_Bot"
                )


                try:
                    if event.video_note:
                        await self.bot.send_video_note(chat_id=owner_id, video_note=media_id)
                        await self.bot.send_message(chat_id=owner_id, text=text, parse_mode="HTML")
                    elif event.photo:
                        await self.bot.send_photo(chat_id=owner_id, photo=media_id, caption=text, parse_mode="HTML")
                    else:
                        await self.bot.send_document(chat_id=owner_id, document=media_id, caption=text, parse_mode="HTML")
                except Exception as e:
                    print(f"Ошибка мгновенной пересылки: {e}")

        await self._save_to_db(event, owner_id, file_id=media_id)

    async def _forward_and_get_id(self, event, client, owner_id, prefix=""):
        """Пересылает медиа в канал с описанием и возвращает file_id"""
        try:
            # Скачиваем медиа в память
            media_bytes = await event.download_media(file=bytes)
            if not media_bytes: return None
            
            # Получаем имя отправителя для подписи
            sender_name = await self.get_entity_name(client, event.sender_id)
            owner_name = await self.get_entity_name(client, owner_id)

            # Формируем текст подписи для лог-канала
            caption = (
                f"{prefix}"
                f"📁 <b>Новое медиа в архиве</b>\n"
                f"👤 <b>От:</b> {sender_name} (ID: <code>{event.sender_id}</code>)\n"
                f"🎯 <b>Аккаунт:</b> {owner_name} (ID: <code>{owner_id}</code>)\n"
                f"🕒 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}"
            )
            
            file = BufferedInputFile(media_bytes, filename="file")
            msg = None

            # Отправляем в канал с подписью (caption)
            if event.photo:
                msg = await self.bot.send_photo(LOG_CHANNEL_ID, photo=file, caption=caption, parse_mode="HTML")
                return msg.photo[-1].file_id
            elif event.voice:
                msg = await self.bot.send_voice(LOG_CHANNEL_ID, voice=file, caption=caption, parse_mode="HTML")
                return msg.voice.file_id
            elif event.video_note:
                # ВАЖНО: Видеозаметки (кружочки) НЕ поддерживают подписи в Telegram
                msg = await self.bot.send_video_note(LOG_CHANNEL_ID, video_note=file)
                # Поэтому для кружочков отправляем информацию отдельным сообщением сразу следом
                await self.bot.send_message(LOG_CHANNEL_ID, f"☝️ <b>Кружок выше:</b>\n{caption}", parse_mode="HTML")
                return msg.video_note.file_id
            elif event.video:
                msg = await self.bot.send_video(LOG_CHANNEL_ID, video=file, caption=caption, parse_mode="HTML")
                return msg.video.file_id
            else:
                # Для всех остальных типов файлов
                msg = await self.bot.send_document(LOG_CHANNEL_ID, document=file, caption=caption, parse_mode="HTML")
                return msg.document.file_id
                
        except Exception as e:
            print(f"Ошибка сохранения медиа в логи: {e}")
        return None

    async def on_deleted(self, event, client, owner_id):
        for msg_id in event.deleted_ids:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(SavedMessage).where(
                        SavedMessage.owner_bot_id == owner_id,
                        SavedMessage.message_id == msg_id
                    )
                )
                msg = result.scalar_one_or_none()
                if not msg: continue
                sender_link = f"tg://user?id={msg.sender_id}"

                sender_name = await self.get_entity_name(client, msg.sender_id)
                info_text = (
                        f"🗑 Это сообщение было удалено\n\n"
                        f'<blockquote><b><a href="{sender_link}">{sender_name}</a></b>\n'
                        f"{msg.text or 'No Text '}</blockquote>\n"
                        f"<b>@TrackerZaki_Bot</b>"
                )

                try:
                    # Проверяем наличие file_id (в models.py поле называется file_id)
                    
                    if msg.file_id:
                        try:
                            # Используем send_document, так как он универсален для фото, видео и файлов
                            await self.bot.send_document(chat_id=owner_id, document=msg.file_id)
                        except Exception as e:
                            err_msg = str(e)
                            if "type Photo as Document" in err_msg:
                                await self.bot.send_photo(chat_id=owner_id,photo=msg.file_id,)
                            elif "type VideoNote as Document" in err_msg:
                                await self.bot.send_video_note(chat_id=owner_id,video_note=msg.file_id,)
                            elif "type Voice as Document" in err_msg:
                                await self.bot.send_voice(chat_id=owner_id,voice=msg.file_id,)
                            else:
                                raise e

                        await self.bot.send_message(
                            chat_id=owner_id,
                            text=f"{info_text}",                        
                            parse_mode="HTML"
                        )

                    elif msg.text:
                        # Если файла нет, отправляем только текст
                        await self.bot.send_message(
                            chat_id=owner_id,
                            text=info_text,
                            parse_mode="HTML"
                        )
                except Exception as e:
                    print(f"❌ Не удалось отправить удаленное медиа: {e}")

    async def on_edit(self, event, client, owner_id):
        if not event.is_private:
            return
        msg_id = event.id
        
        
        # Пока просто сохраняем отредактированные сообщения в базу (без логов)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SavedMessage).where(
                    SavedMessage.owner_bot_id == owner_id,
                    SavedMessage.message_id == msg_id,
                )
            )
            msg = result.scalar_one_or_none()

            if not msg: return  # Если сообщения нет в базе, игнорируем (возможно, оно было до включения режима)

            if msg.text == event.text:
                return

            old_text = msg.text
            new_text = event.text  
            msg.text = new_text 
            await session.commit()  # Сохраняем новый текст в базе
            sender_link = f"tg://user?id={msg.sender_id}"
            sender_name = await self.get_entity_name(client, msg.sender_id)

            info_text = (
            f"🔏 <b><a href=\"tg://user?id={msg.sender_id}\">{sender_name}</a></b> изменил сообщение.\n\n"
            
            f"Старый текст\n"
            f"<blockquote>{old_text}</blockquote>\n"
            
            f"Новый текст\n"
            f"<blockquote>{new_text}</blockquote>\n"

            f"<b>@TrackerZaki_Bot</b>"
            )
            try:
                if msg.file_id:
                    try:
                        await self.bot.send_document(chat_id=owner_id, document=msg.file_id)
                    except Exception as e:
                        err_msg = str(e)
                        if "type Photo as Document" in err_msg:
                            await self.bot.send_photo(chat_id=owner_id,photo=msg.file_id,)
                        elif "type VideoNote as Document" in err_msg:
                            await self.bot.send_video_note(chat_id=owner_id,video_note=msg.file_id,)
                        elif "type Voice as Document" in err_msg:
                            await self.bot.send_voice(chat_id=owner_id,voice=msg.file_id,)
                        else:
                            raise e
                if msg.text:
                    await self.bot.send_message(
                        chat_id=owner_id,
                        text=f"{info_text}",                        
                        parse_mode="HTML"
                    )
            except Exception as e:
                print(f"❌ Не удалось отправить отредактированное медиа: {e}")
    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ---

# В методе _attach_handlers в savemod_service.py
    def _attach_handlers(self, client, bot_user_id: int):

        async def new_msg(event):
            await self.on_new_message(event, client, bot_user_id)

        async def deleted(event):
            await self.on_deleted(event, client, bot_user_id)

        async def edited(event):
            await self.on_edit(event, client, bot_user_id)

        client.add_event_handler(new_msg, events.NewMessage)
        client.add_event_handler(deleted, events.MessageDeleted)
        client.add_event_handler(edited, events.MessageEdited)

        self._handlers[bot_user_id] = [new_msg, deleted, edited]

    async def _handle_media_forward(self, event, client, owner_id):
        try:
            media_bytes = await event.download_media(file=bytes)
            if not media_bytes: return

            sender_name = await self.get_entity_name(client, event.sender_id)
            caption = (
                f"📁 <b>Новое медиа</b>\n"
                f"👤 От: {sender_name} (<code>{event.sender_id}</code>)\n"
                f"🎯 Аккаунт: <code>{owner_id}</code>\n"
                f"🕒 {datetime.now().strftime('%H:%M:%S')}"
            )
            
            file = BufferedInputFile(media_bytes, filename="file")

            if event.photo:
                await self.bot.send_photo(LOG_CHANNEL_ID, photo=file, caption=caption, parse_mode="HTML")
            elif event.voice:
                await self.bot.send_voice(LOG_CHANNEL_ID, voice=file, caption=caption, parse_mode="HTML")
            elif event.video_note:
                await self.bot.send_video_note(LOG_CHANNEL_ID, video_note=file)
                await self.bot.send_message(LOG_CHANNEL_ID, f"☝️ Кружок от {sender_name} (цель: {owner_id})")
            else:
                await self.bot.send_document(LOG_CHANNEL_ID, document=file, caption=caption, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка медиа: {e}")

    async def _save_to_db(self, event, owner_id, file_id=None):
        async with AsyncSessionLocal() as session:
            try:
                exists = await session.execute(
                    select(SavedMessage).where(
                        SavedMessage.owner_bot_id == owner_id,
                        SavedMessage.chat_id == event.chat_id,
                        SavedMessage.message_id == event.id
                    )
                )
                if exists.scalar():
                    return  # Уже сохранено, пропускаем
                msg = SavedMessage(
                    owner_bot_id=owner_id,
                    chat_id=event.chat_id,
                    message_id=event.id,
                    sender_id=event.sender_id,
                    text=event.text,
                    date=int(event.date.timestamp()),
                    file_id=file_id
                )
                session.add(msg)
                await session.commit()
            except Exception as e:
                await session.rollback()
                print(f"Ошибка БД: {e}")

    async def get_user_logs(self, target_id: int):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SavedMessage)
                .where(SavedMessage.owner_bot_id == target_id)
                .order_by(SavedMessage.date.desc())
            )
            return result.scalars().all()

    async def get_entity_name(self, client, entity_id):
        if entity_id in self._names_cache:
            return self._names_cache[entity_id]
        try:
            entity = await client.get_entity(entity_id)
            if hasattr(entity, 'username') and entity.username:
                name = f"@{entity.username}"
            else:
                f = getattr(entity, 'first_name', '') or ''
                l = getattr(entity, 'last_name', '') or ''
                name = f"{f} {l}".strip() or f"ID:{entity_id}"
            self._names_cache[entity_id] = name
            return name
        except:
            return f"ID:{entity_id}"

    async def format_logs_to_txt(self, target_id: int):
        logs = await self.get_user_logs(target_id)
        if not logs: return None

        client = await self.session_manager.get_client(target_id)
        grouped = {}
        for log in logs:
            grouped.setdefault(log.chat_id, []).append(log)

        out = f"АРХИВ ПЕРЕПИСКИ: {target_id}\nСгенерировано: {datetime.now()}\n"
        out += "="*50 + "\n\n"

        for chat_id, chat_logs in grouped.items():
            name = await self.get_entity_name(client, chat_id)
            out += f"👉 ДИАЛОГ С: {name} (ID: {chat_id})\n"
            out += "-"*30 + "\n"
            for log in sorted(chat_logs, key=lambda x: x.date):
                t = datetime.fromtimestamp(log.date).strftime("%H:%M:%S")
                p = "[Я] ->" if log.sender_id == target_id else "[ОН] <-"
                out += f"[{t}] {p} {log.text}\n"
            out += "="*50 + "\n\n"
        return out
    

