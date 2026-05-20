import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

from sqlalchemy import select

from config import API_ID, API_HASH
from db.session import AsyncSessionLocal
from db.models import UserSession

# Правильный logger
logger = logging.getLogger(__name__)


class AuthService:

    def __init__(self):
        # временные клиенты во время авторизации
        self.temp_clients: dict[int, TelegramClient] = {}

    # =========================
    # Отправка кода
    # =========================
    async def send_code(self, user_id: int, phone: str):
        # Удаляем старый клиент если есть
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
            logger.info(f"[Auth] Код отправлен на {phone} для user_id={user_id}")
            phone_code_hash = result.phone_code_hash
        except Exception as e:
            logger.error(f"[Auth] Ошибка отправки кода на {phone}: {e}")
            raise

        self.temp_clients[user_id] = client
        return phone_code_hash

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
        logger.info(f"[Auth] Попытка sign_in для user_id: {user_id}")

        client = self.temp_clients.get(user_id)
        if not client:
            raise Exception(f"Auth session expired для user_id {user_id}")

        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )

            session_string = client.session.save()

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(UserSession).where(UserSession.bot_user_id == user_id)
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

            self.temp_clients.pop(user_id, None)
            logger.info(f"[Auth] sign_in УСПЕШНО для user_id: {user_id}")
            return "OK"

        except SessionPasswordNeededError:
            logger.info(f"[Auth] Требуется 2FA пароль для user_id: {user_id}")
            return "PASSWORD_REQUIRED"

        except Exception as e:
            logger.error(f"[Auth] sign_in ошибка для user_id {user_id}: {e}")
            raise

    # =========================
    # Вход по паролю (2FA)
    # =========================
    async def sign_in_with_password(self, user_id: int, password: str):
        logger.info(f"[Auth] Попытка sign_in_with_password для user_id: {user_id}")

        client = self.temp_clients.get(user_id)
        if not client:
            raise Exception(f"Auth session expired для 2FA user_id {user_id}")

        try:
            await client.sign_in(password=password)

            session_string = client.session.save()

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(UserSession).where(UserSession.bot_user_id == user_id)
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
            logger.info(f"[Auth] sign_in_with_password УСПЕШНО для user_id: {user_id}")
            return "OK"

        except Exception as e:
            logger.error(f"[Auth] sign_in_with_password ошибка для user_id {user_id}: {e}")
            raise