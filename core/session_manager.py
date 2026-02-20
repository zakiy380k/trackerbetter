from telethon import TelegramClient
from telethon.sessions import StringSession
from sqlalchemy import select

from config import API_ID, API_HASH
from db.session import AsyncSessionLocal
from db.models import UserSession

from sqlalchemy import select
from db.session import AsyncSessionLocal
from db.models import UserSession
class SessionManager:

    def __init__(self):
        self.clients: dict[int, TelegramClient] = {}

    # Получить клиент
    async def get_client(self, user_id: int):

        # Если уже загружен в память
        if user_id in self.clients:
            return self.clients[user_id]

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSession).where(
                    UserSession.bot_user_id == user_id
                )
            )
            user = result.scalar_one_or_none()

        if not user or not user.session_string:
            return None

        client = TelegramClient(
            StringSession(user.session_string),
            API_ID,
            API_HASH,
            flood_sleep_threshold=60
        )

        await client.connect()

        self.clients[user_id] = client
        return client


    # Сохранить session_string после логина
    async def save_session(self, user_id: int, client: TelegramClient):

        session_string = client.session.save()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSession).where(
                    UserSession.bot_user_id == user_id
                )
            )

            user = result.scalar_one_or_none()

            if not user:
                user = UserSession(
                    bot_user_id=user_id
                )
                db.add(user)

            user.session_string = session_string
            await db.commit()

        self.clients[user_id] = client


    # Восстановить все сессии при старте
    async def restore_all_sessions(self):

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(UserSession))
            users = result.scalars().all()

        for user in users:
            if not user.session_string:
                continue

            try:
                client = TelegramClient(
                    StringSession(user.session_string),
                    API_ID,
                    API_HASH
                )

                await client.connect()

                self.clients[user.bot_user_id] = client
                print(f"✅ Restored {user.bot_user_id}")

            except Exception as e:
                print(f"❌ Restore error {user.bot_user_id}: {e}")


    async def logout(self, user_id: int):

        client = self.clients.pop(user_id, None)

        if client:
            await client.log_out()
            await client.disconnect()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSession).where(
                    UserSession.bot_user_id == user_id
                )
            )
            user = result.scalar_one_or_none()

            if user:
                user.session_string = None
                await db.commit()

    async def has_session(self, user_id: int) -> bool:

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSession).where(
                    UserSession.bot_user_id == user_id,
                    UserSession.session_string.is_not(None)
                )
            )

            user = result.scalar_one_or_none()

        return user is not None