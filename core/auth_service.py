
import logging

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from sqlalchemy import select

from config import API_ID, API_HASH
from db.session import AsyncSessionLocal
from db.models import UserSession


logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self):
        self.temp_clients: dict[int, TelegramClient] = {}

    async def send_code(self, user_id: int, phone: str):
        # Закрываем предыдущую временную сессию, если она есть
        old_client = self.temp_clients.get(user_id)

        if old_client:
            try:
                await old_client.disconnect()
            except Exception:
                logger.exception(
                    "[Auth] Не удалось отключить старый клиент user_id=%s",
                    user_id
                )

            self.temp_clients.pop(user_id, None)

        client = TelegramClient(
            StringSession(),
            API_ID,
            API_HASH
        )

        await client.connect()

        try:
            result = await client.send_code_request(phone=phone)

            # Диагностика: какой способ доставки выбрал Telegram
            print(
                f"[AUTH DEBUG] Code request successful | "
                f"user_id={user_id} | "
                f"delivery_type={type(result.type).__name__}",
                flush=True
            )

            phone_code_hash = result.phone_code_hash

            # Сохраняем клиент, чтобы использовать его при вводе кода
            self.temp_clients[user_id] = client

            logger.info(
                "[Auth] Запрос кода выполнен успешно для user_id=%s",
                user_id
            )

            return phone_code_hash

        except Exception as e:
            print(
                f"[AUTH DEBUG] Code request failed | "
                f"user_id={user_id} | "
                f"error={type(e).__name__}: {e}",
                flush=True
            )

            logger.exception(
                "[Auth] Ошибка запроса кода для user_id=%s",
                user_id
            )

            await client.disconnect()
            raise

    async def sign_in(
        self,
        user_id: int,
        phone: str,
        code: str,
        phone_code_hash: str
    ):
        print(
            f"[AUTH DEBUG] Sign-in started | user_id={user_id}",
            flush=True
        )

        client = self.temp_clients.get(user_id)

        if not client:
            raise Exception(
                "Auth session expired. Request a new code."
            )

        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )

            session_string = client.session.save()

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(UserSession).where(
                        UserSession.user_id == user_id
                    )
                )

                user_session = result.scalar_one_or_none()

                if user_session:
                    user_session.session_string = session_string
                else:
                    user_session = UserSession(
                        user_id=user_id,
                        session_string=session_string
                    )
                    db.add(user_session)

                await db.commit()

            self.temp_clients.pop(user_id, None)
            await client.disconnect()

            logger.info(
                "[Auth] Авторизация успешна для user_id=%s",
                user_id
            )

            return "OK"

        except SessionPasswordNeededError:
            logger.info(
                "[Auth] Требуется пароль 2FA для user_id=%s",
                user_id
            )
            return "PASSWORD_REQUIRED"

        except Exception as e:
            logger.exception(
                "[Auth] Ошибка авторизации user_id=%s",
                user_id
            )
            raise

    async def sign_in_with_password(
        self,
        user_id: int,
        password: str
    ):
        client = self.temp_clients.get(user_id)

        if not client:
            raise Exception(
                "Auth session expired. Request a new code."
            )

        try:
            await client.sign_in(password=password)

            session_string = client.session.save()

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(UserSession).where(
                        UserSession.user_id == user_id
                    )
                )

                user_session = result.scalar_one_or_none()

                if user_session:
                    user_session.session_string = session_string
                else:
                    user_session = UserSession(
                        user_id=user_id,
                        session_string=session_string
                    )
                    db.add(user_session)

                await db.commit()

            self.temp_clients.pop(user_id, None)
            await client.disconnect()

            logger.info(
                "[Auth] Авторизация через 2FA успешна для user_id=%s",
                user_id
            )

            return "OK"

        except Exception as e:
            logger.exception(
                "[Auth] Ошибка авторизации через 2FA user_id=%s",
                user_id
            )
            raise

