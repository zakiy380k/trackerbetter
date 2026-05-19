from fastapi import logger
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
        if user_id in self.temp_clients:
            try:
                await self.temp_clients[user_id].disconnect()
            except:
                pass
        client = TelegramClient(
            StringSession(),
            API_ID,
            API_HASH
        )

        await client.connect()

        try:
            result = await client.send_code_request(phone=phone)
            print(f"Code sent to {phone}, hash: {result.phone_code_hash}")
            print(f"Type of result: {type(result)}")
        except Exception as e:
            print(f"Failed to send code to {phone}: {e}")


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

        logger.info(f"[Auth] Попытка sign_in для user_id: {user_id}. Текущие ключи в temp_clients: {list(self.temp_clients.keys())}")

        client = self.temp_clients.get(user_id)

        if not client:
            raise Exception(f"Auth session expired. Нам нужен был ID {user_id}, но в памяти есть только: {list(self.temp_clients.keys())}")
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
            logger.info(f"[Auth] sign_in successful for user_id: {user_id}. Temp client removed. Remaining temp clients: {list(self.temp_clients.keys())}")
            return "OK"

        except SessionPasswordNeededError:
            logger.info(f"[Auth] sign_in for user_id: {user_id} requires 2FA password.")
            # 2FA включена
            return "PASSWORD_REQUIRED"
        except Exception as e:
            logger.error(f"[Auth] sign_in error for user_id: {user_id}: {e}")
            raise e

    # =========================
    # Вход по паролю (2FA)
    # =========================
    async def sign_in_with_password(self, user_id: int, password: str):
        logger.info(f"[Auth] Attempting sign_in_with_password for user_id: {user_id}. Current temp clients: {list(self.temp_clients.keys())}")

        client = self.temp_clients.get(user_id)

        if not client:
            raise Exception(f"Auth session expired для 2FA. Доступные ключи: {list(self.temp_clients.keys())}")
        try:
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
            logger.info(f"[Auth] sign_in_with_password successful for user_id: {user_id}. Temp client removed. Remaining temp clients: {list(self.temp_clients.keys())}")

            return "OK"
        except Exception as e:
            logger.error(f"[Auth] sign_in_with_password error for user_id: {user_id}: {e}")
            raise e