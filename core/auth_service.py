from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

from sqlalchemy import select

from config import API_ID, API_HASH
from db.session import AsyncSessionLocal
from db.models import UserSession


class AuthService:

    def __init__(self):
        # временные клиенты во время авторизации
        self.temp_clients: dict[int, TelegramClient] = {}

    # =========================
    # Отправка кода
    # =========================
    async def send_code(self, user_id: int, phone: str):

        client = TelegramClient(
            StringSession(),
            API_ID,
            API_HASH
        )

        await client.connect()

        result = await client.send_code_request(phone=phone)

        # сохраняем client (ВАЖНО!)
        self.temp_clients[user_id] = client

        return result.phone_code_hash

    # =========================
    # Вход по коду
    # =========================
    async def sign_in(
        self,
        user_id: int,
        phone: str,
        code: str,
        phone_code_hash: str
    ):

        client = self.temp_clients.get(user_id)

        if not client:
            raise Exception("Auth session expired. Request code again.")

        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )

            # ⭐ сохраняем StringSession
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
                        bot_user_id=user_id,
                        phone=phone,
                        savemod_enabled=False
                    )
                    db.add(user)

                user.session_string = session_string
                await db.commit()

            # клиент больше не временный
            self.temp_clients.pop(user_id, None)

            return "OK"

        except SessionPasswordNeededError:
            # 2FA включена
            return "PASSWORD_REQUIRED"

    # =========================
    # Вход по паролю (2FA)
    # =========================
    async def sign_in_with_password(self, user_id: int, password: str):

        client = self.temp_clients.get(user_id)

        if not client:
            raise Exception("Auth session expired")

        await client.sign_in(password=password)

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
                    bot_user_id=user_id,
                    phone=None,
                    savemod_enabled=False
                )
                db.add(user)

            user.session_string = session_string
            await db.commit()

        self.temp_clients.pop(user_id, None)

        return "OK"