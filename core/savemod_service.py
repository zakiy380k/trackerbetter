from telethon import events
from sqlalchemy import select

from db.session import AsyncSessionLocal
from db.models import SavedMessage, UserSession


class SaveModService:
    def __init__(self, bot,session_manager):
        self.session_manager = session_manager
        self.bot = bot
        self._attached_clients = set()


    async def enable(self, bot_user_id: int):
        client = await self.session_manager.get_client(bot_user_id)
        if client is None:
            raise RuntimeError("❌ Сначала авторизуйся (/auth)")

        # включаем флаг в БД
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSession).where(
                    UserSession.bot_user_id == bot_user_id
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                raise RuntimeError("❌ Пользователь не найден в БД")

            user.savemod_enabled = True
            await session.commit()

        # навешиваем handlers ОДИН РАЗ
        if bot_user_id not in self._attached_clients:
            self._attach_handlers(client, bot_user_id)
            self._attached_clients.add(bot_user_id)

    async def disable(self, bot_user_id: int):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserSession).where(
                    UserSession.bot_user_id == bot_user_id
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                raise RuntimeError("❌ Пользователь не найден")

            user.savemod_enabled = False
            await session.commit()

    # ==========================
    # TELETHON HANDLERS
    # ==========================
    def _attach_handlers(self, client, bot_user_id: int):

        @client.on(events.NewMessage)
        async def on_new_message(event):
            print("EVent")
            if not event.is_private or not event.text:
                return

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(UserSession.savemod_enabled).where(
                        UserSession.bot_user_id == bot_user_id
                    )
                )
                if not result.scalar():
                    return

                msg = SavedMessage(
                    owner_bot_id=bot_user_id,
                    chat_id=event.chat_id,
                    message_id=event.id,
                    sender_id=event.sender_id,
                    text=event.text,
                    date=int(event.date.timestamp())
                )
                session.add(msg)
                await session.commit()

                print("[SaveMod] saved:", event.text)

        @client.on(events.MessageDeleted)
        async def on_deleted(event):
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(UserSession.savemod_enabled).where(
                        UserSession.bot_user_id == bot_user_id
                    )
                )
                if not result.scalar():
                    return

                for msg_id in event.deleted_ids:
                    result = await session.execute(
                        select(SavedMessage).where(
                            SavedMessage.owner_bot_id == bot_user_id,
                            SavedMessage.message_id == msg_id
                        )
                    )
                    msg = result.scalar_one_or_none()   
                    if not msg:
                        continue

                    try:
                        sender = await client.get_entity(msg.sender_id)
                        username = (
                            f"@{sender.username}"
                            if sender.username
                            else f"{sender.first_name or ''} {sender.last_name or ''}".strip()
                        )
                    except Exception:
                        username = f"ID:{msg.sender_id}"

                  
                    await self.bot.send_message(
                        chat_id=bot_user_id,
                        text=(
                            "🗑 <b>Сообщение удалено</b>\n\n"
                            f"👤 <b>От:</b> {username}\n"
                            f"💬 <b>Текст:</b>\n{msg.text}"
                        ),
                        parse_mode="HTML"
                    )